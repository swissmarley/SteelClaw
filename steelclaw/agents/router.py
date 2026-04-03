"""Agent router — LLM-powered agent with tool calling, skills, and persistent context."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.agents.persona_loader import build_persona_system_prompt
from steelclaw.db.models import Session as DBSession
from steelclaw.llm.context import ContextBuilder
from steelclaw.llm.provider import LLMProvider, LLMResponse, StreamChunk, ToolCall
from steelclaw.pricing import calculate_cost
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings
from steelclaw.skills.registry import SkillRegistry

logger = logging.getLogger("steelclaw.agents")

# Maximum tool-call iterations to prevent infinite loops
MAX_TOOL_ROUNDS = 10
# OpenAI and most providers cap tools at 128
MAX_TOOLS = 128


@dataclass
class AgentResponse:
    """Extended response carrying both the outbound message and usage metadata."""

    outbound: OutboundMessage
    model: str | None = None
    token_usage_prompt: int = 0
    token_usage_completion: int = 0
    cost_usd: float = 0.0


class AgentRouter:
    """Routes messages to the LLM with tool-calling support.

    Pipeline:
    1. Build conversation context from DB history + skill system prompts
    2. Call LLM with available tools from loaded skills
    3. If LLM returns tool calls → execute tools → feed results back → repeat
    4. Return final text response with accumulated usage stats
    """

    def __init__(
        self,
        settings: AgentSettings,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._provider = LLMProvider(settings.llm)
        self._context = ContextBuilder(settings.llm)
        self._skills = skill_registry
        self._memory_retriever = None
        self._memory_ingestor = None

    def set_memory(self, retriever, ingestor) -> None:
        """Inject memory components after initialisation."""
        self._memory_retriever = retriever
        self._memory_ingestor = ingestor

    async def route(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> OutboundMessage:
        """Process a message through the LLM agent pipeline. Returns OutboundMessage."""
        result = await self.route_with_usage(message, session, db)
        return result.outbound

    async def route_with_usage(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> AgentResponse:
        """Process a message and return response with usage metadata."""
        try:
            response_text, usage = await self._run_agent_loop(message, session, db)
        except Exception as e:
            logger.exception("Agent error for session %s", session.id)
            response_text = f"I encountered an error: {e}"
            usage = {"model": None, "prompt_tokens": 0, "completion_tokens": 0}

        outbound = OutboundMessage(
            platform=message.platform,
            platform_chat_id=message.platform_chat_id,
            content=response_text,
            reply_to_message_id=message.platform_message_id,
        )

        model = usage.get("model")
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return AgentResponse(
            outbound=outbound,
            model=model,
            token_usage_prompt=prompt_tokens,
            token_usage_completion=completion_tokens,
            cost_usd=calculate_cost(model, prompt_tokens, completion_tokens),
        )

    async def _run_agent_loop(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> tuple[str, dict]:
        """Run the agentic loop. Returns (response_text, accumulated_usage)."""

        # Build context with optional memory injection
        skill_context = self._skills.get_combined_system_context() if self._skills else None
        tools_schema = self._skills.get_all_tools_schema() if self._skills else []

        # Cap tools at MAX_TOOLS to avoid API errors (OpenAI limit is 128)
        if len(tools_schema) > MAX_TOOLS:
            tools_schema = self._select_relevant_tools(
                message.content, tools_schema,
            )

        # Retrieve relevant memories scoped to this session's namespace
        memory_context = None
        if self._memory_retriever and message.content:
            namespace = getattr(session, "unified_session_id", None) or session.id
            memories = self._memory_retriever.retrieve_relevant(
                query_text=message.content,
                namespace=namespace,
                limit=self._settings.memory.top_k,
            )
            memory_context = self._memory_retriever.format_for_prompt(memories)

        # Build persona prompt fresh every turn (survives context resets)
        persona_prompt = build_persona_system_prompt()

        if db is not None:
            messages = await self._context.build(
                session=session,
                db=db,
                persona_prompt=persona_prompt,
                skill_context=skill_context,
                memory_context=memory_context,
                current_message=message.content,
                attachments=message.attachments,
            )
        else:
            # Fallback: no DB, just persona + system + current message
            system = f"{persona_prompt}\n\n{self._settings.llm.system_prompt}"
            if skill_context:
                system = f"{system}\n\n{skill_context}"
            if memory_context:
                system = f"{system}\n\n{memory_context}"
            messages = [
                {"role": "system", "content": system},
                self._context._build_user_message(message.content, message.attachments),
            ]

        # Accumulate token usage across all rounds
        total_prompt = 0
        total_completion = 0
        model_used = None

        # Agent loop with tool calling
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self._provider.complete(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            # Accumulate usage
            model_used = response.model or model_used
            total_prompt += response.usage.get("prompt_tokens", 0)
            total_completion += response.usage.get("completion_tokens", 0)

            # If no tool calls, return the text response
            if not response.tool_calls:
                usage = {
                    "model": model_used,
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                }
                return response.content or "(no response)", usage

            # Process tool calls
            logger.info(
                "Agent round %d: %d tool call(s)",
                round_num + 1,
                len(response.tool_calls),
            )

            # Add assistant message with tool calls to context
            messages.append(
                self._context.build_assistant_tool_call_message(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # Execute each tool call and add results
            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc)
                messages.append(
                    self._context.build_tool_result_message(tc.id, result)
                )

        # Exhausted tool rounds
        logger.warning("Agent exhausted %d tool rounds", MAX_TOOL_ROUNDS)
        usage = {
            "model": model_used,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        }
        return (
            response.content or "I've been working on this but reached my iteration limit. Here's what I have so far.",
            usage,
        )

    def _select_relevant_tools(
        self, message_content: str, all_tools: list[dict],
    ) -> list[dict]:
        """Select the most relevant tools when total exceeds MAX_TOOLS.

        Strategy:
        1. Find skills matching message triggers — include all their tools first
        2. Fill remaining slots with core skills (shell, web_search, notes, etc.)
        3. Fill any remaining slots from the rest in order
        """
        if not self._skills:
            return all_tools[:MAX_TOOLS]

        # Get names of skills whose triggers match the message
        matched_skills = self._skills.find_skills_by_trigger(message_content)
        matched_skill_names = {s.name for s in matched_skills}

        # Core skills that should always be included
        core_skills = {
            "shell", "web_search", "notes", "calculator", "file_manager",
            "reminder", "system_info", "browser", "cron_manager",
        }

        # Build tool name → skill name index
        tool_to_skill: dict[str, str] = {}
        for skill_name, skill in self._skills.skills.items():
            for tool in skill.tools:
                tool_to_skill[tool.name] = skill_name

        # Partition tools into priority buckets
        triggered: list[dict] = []
        core: list[dict] = []
        rest: list[dict] = []

        for tool_schema in all_tools:
            tool_name = tool_schema.get("function", {}).get("name", "")
            skill_name = tool_to_skill.get(tool_name, "")
            if skill_name in matched_skill_names:
                triggered.append(tool_schema)
            elif skill_name in core_skills:
                core.append(tool_schema)
            else:
                rest.append(tool_schema)

        # Assemble up to MAX_TOOLS
        selected = triggered[:MAX_TOOLS]
        remaining = MAX_TOOLS - len(selected)
        if remaining > 0:
            selected.extend(core[:remaining])
            remaining = MAX_TOOLS - len(selected)
        if remaining > 0:
            selected.extend(rest[:remaining])

        logger.info(
            "Tool selection: %d triggered, %d core, %d other → %d total (from %d)",
            len(triggered), min(len(core), MAX_TOOLS - len(triggered)),
            max(0, len(selected) - len(triggered) - len(core)),
            len(selected), len(all_tools),
        )
        return selected

    async def stream_response(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> AsyncIterator[dict]:
        """Stream agent response as chunks. Yields dicts:

        - {"type": "chunk", "content": "text"}  — incremental text
        - {"type": "tool_start", "name": "...", "id": "..."}  — tool call starting
        - {"type": "tool_end", "name": "...", "result_preview": "..."}  — tool call done
        - {"type": "done", "content": "full text", "usage": {...}}  — final
        - {"type": "error", "content": "..."}  — on failure
        """
        try:
            async for event in self._stream_agent_loop(message, session, db):
                yield event
        except Exception as e:
            logger.exception("Streaming agent error for session %s", session.id)
            yield {"type": "error", "content": f"I encountered an error: {e}"}

    async def _stream_agent_loop(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> AsyncIterator[dict]:
        """Streaming agentic loop. Yields events as chunks arrive."""

        # Build context (same as non-streaming)
        skill_context = self._skills.get_combined_system_context() if self._skills else None
        tools_schema = self._skills.get_all_tools_schema() if self._skills else []

        if len(tools_schema) > MAX_TOOLS:
            tools_schema = self._select_relevant_tools(message.content, tools_schema)

        memory_context = None
        if self._memory_retriever and message.content:
            namespace = getattr(session, "unified_session_id", None) or session.id
            memories = self._memory_retriever.retrieve_relevant(
                query_text=message.content,
                namespace=namespace,
                limit=self._settings.memory.top_k,
            )
            memory_context = self._memory_retriever.format_for_prompt(memories)

        persona_prompt = build_persona_system_prompt()

        if db is not None:
            messages = await self._context.build(
                session=session,
                db=db,
                persona_prompt=persona_prompt,
                skill_context=skill_context,
                memory_context=memory_context,
                current_message=message.content,
                attachments=message.attachments,
            )
        else:
            system = f"{persona_prompt}\n\n{self._settings.llm.system_prompt}"
            if skill_context:
                system = f"{system}\n\n{skill_context}"
            if memory_context:
                system = f"{system}\n\n{memory_context}"
            messages = [
                {"role": "system", "content": system},
                self._context._build_user_message(message.content, message.attachments),
            ]

        total_prompt = 0
        total_completion = 0
        model_used = None
        full_content = ""

        for round_num in range(MAX_TOOL_ROUNDS):
            # Accumulate streaming chunks
            content_buffer = ""
            tool_call_buffers: dict[int, dict] = {}  # index → {id, name, arguments_str}
            finish_reason = None

            async for chunk in self._provider.stream(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            ):
                # Text content — yield immediately
                if chunk.content:
                    content_buffer += chunk.content
                    yield {"type": "chunk", "content": chunk.content}

                # Tool call delta — accumulate
                if chunk.tool_call_delta:
                    td = chunk.tool_call_delta
                    idx = td.get("index", 0)
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {
                            "id": td.get("id", ""),
                            "name": td.get("name", ""),
                            "arguments_str": "",
                        }
                    buf = tool_call_buffers[idx]
                    if td.get("id"):
                        buf["id"] = td["id"]
                    if td.get("name"):
                        buf["name"] = (buf["name"] or "") + td["name"]
                    if td.get("arguments"):
                        buf["arguments_str"] += td["arguments"]

                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason

            full_content += content_buffer

            # Parse accumulated tool calls
            tool_calls: list[ToolCall] = []
            for idx in sorted(tool_call_buffers.keys()):
                buf = tool_call_buffers[idx]
                try:
                    args = json.loads(buf["arguments_str"]) if buf["arguments_str"] else {}
                except json.JSONDecodeError:
                    args = {"raw": buf["arguments_str"]}
                tool_calls.append(ToolCall(id=buf["id"], name=buf["name"], arguments=args))

            # No tool calls → we're done
            if not tool_calls:
                usage = {
                    "model": model_used,
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                }
                yield {"type": "done", "content": full_content or "(no response)", "usage": usage}
                return

            # Execute tool calls
            logger.info("Stream round %d: %d tool call(s)", round_num + 1, len(tool_calls))

            messages.append(
                self._context.build_assistant_tool_call_message(
                    content=content_buffer,
                    tool_calls=tool_calls,
                )
            )

            for tc in tool_calls:
                yield {"type": "tool_start", "name": tc.name, "id": tc.id}
                result = await self._execute_tool_call(tc)
                messages.append(
                    self._context.build_tool_result_message(tc.id, result)
                )
                yield {
                    "type": "tool_end",
                    "name": tc.name,
                    "result_preview": result[:200],
                }

        # Exhausted tool rounds
        usage = {
            "model": model_used,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        }
        yield {
            "type": "done",
            "content": full_content or "I've been working on this but reached my iteration limit.",
            "usage": usage,
        }

    async def _execute_tool_call(self, tc: ToolCall) -> str:
        """Execute a single tool call via the skill registry."""
        if self._skills is None:
            return f"Error: No skill registry available to execute tool '{tc.name}'"

        logger.info("Executing tool: %s(%s)", tc.name, json.dumps(tc.arguments)[:200])
        result = await self._skills.execute_tool(tc.name, tc.arguments)
        logger.debug("Tool result: %s", result[:500])
        return result
