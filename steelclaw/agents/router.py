"""Agent router — LLM-powered agent with tool calling, skills, and persistent context."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from copy import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.agents.persona_loader import build_persona_system_prompt
from steelclaw.db.models import Session as DBSession
from steelclaw.security.context import set_security_context, clear_security_context
from steelclaw.llm.context import ContextBuilder
from steelclaw.llm.provider import LLMProvider, LLMResponse, StreamChunk, ToolCall
from steelclaw.pricing import calculate_cost
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings
from steelclaw.skills.registry import SkillRegistry
from steelclaw.security.context import set_security_context, clear_security_context

logger = logging.getLogger("steelclaw.agents")

# OpenAI and most providers cap tools at 128
MAX_TOOLS = 128

# Module-level set that tracks all live reflection background tasks across ALL
# AgentRouter instances.  Each request creates a fresh router, so per-instance
# tracking alone is insufficient: the router is GC'd after the response is
# returned, which could silently cancel its tasks before they finish.
# Using a module-level set gives app.py a single place to drain on shutdown.
_active_background_tasks: set[asyncio.Task] = set()


async def drain_background_tasks(timeout: float = 10.0) -> None:
    """Await all active reflection tasks, with a graceful timeout.

    Called from the app lifespan shutdown sequence so that in-progress
    skill-file writes and ReflectionLog entries can complete cleanly.
    """
    pending = list(_active_background_tasks)
    if not pending:
        return
    logger.info("Draining %d background reflection task(s)…", len(pending))
    done, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        logger.warning(
            "%d background task(s) did not finish within %.1fs; cancelling.",
            len(still_running), timeout,
        )
        for t in still_running:
            t.cancel()
        await asyncio.gather(*still_running, return_exceptions=True)
    else:
        # Gather exceptions from completed tasks to prevent silent failures
        await asyncio.gather(*done, return_exceptions=True)


# Regex to strip<think>...</think> reasoning blocks from LLM responses.
# These are internal reasoning traces that must not appear in user-facing output.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> blocks from *text* and return cleaned output."""
    cleaned = _THINK_RE.sub("", text)
    # Normalise leftover blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_think_blocks(text: str) -> list[str]:
    """Return the content of all <think>...</think> blocks (for debug logging)."""
    return _THINK_RE.findall(text)


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
        agent_profile=None,  # Optional[AgentProfile] — uses DB-stored model/prompt/persona
    ) -> None:
        self._settings = settings
        self._profile = agent_profile
        self._skills = skill_registry
        self._memory_retriever = None
        self._memory_ingestor = None
        self._skill_generator = None  # Optional[SkillGenerator] — set via set_skill_generator()
        # Tracks live background reflection tasks so they are not garbage-collected
        # mid-execution and can be awaited during graceful shutdown.
        self._background_tasks: set[asyncio.Task] = set()

        # Apply per-agent model/temperature overrides when a profile is provided
        llm_settings = settings.llm
        if agent_profile is not None:
            if agent_profile.model_override or agent_profile.temperature_override is not None:
                llm_settings = copy(settings.llm)
                if agent_profile.model_override:
                    llm_settings.default_model = agent_profile.model_override
                if agent_profile.temperature_override is not None:
                    llm_settings.temperature = agent_profile.temperature_override

        self._provider = LLMProvider(llm_settings)
        self._context = ContextBuilder(llm_settings)

    def set_memory(self, retriever, ingestor) -> None:
        """Inject memory components after initialisation."""
        self._memory_retriever = retriever
        self._memory_ingestor = ingestor

    def set_skill_generator(self, generator) -> None:
        """Inject the skill generator for autonomous skill creation."""
        self._skill_generator = generator

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
        on_tool_event=None,
        extra_tools: list[dict] | None = None,
    ) -> AgentResponse:
        """Process a message and return response with usage metadata.

        ``on_tool_event`` is an optional async callable invoked with a dict
        matching the same tool_start / tool_end schema used by the streaming
        layer, enabling platform connectors to show real-time tool feedback.

        ``extra_tools`` is an optional list of additional tool schemas to prepend
        (e.g. the orchestrator's ``delegate_to_subagent`` tool).
        """
        # Set security context for permission checks
        set_security_context(
            session_id=str(session.id),
            platform=message.platform,
            platform_chat_id=message.platform_chat_id,
        )
        try:
            response_text, usage = await self._run_agent_loop(
                message, session, db, on_tool_event=on_tool_event, extra_tools=extra_tools
            )
        except Exception as e:
            logger.exception("Agent error for session %s", session.id)
            response_text = f"I encountered an error: {e}"
            usage = {"model": None, "prompt_tokens": 0, "completion_tokens": 0}
        finally:
            clear_security_context()

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
        on_tool_event=None,
        extra_tools: list[dict] | None = None,
    ) -> tuple[str, dict]:
        """Run the agentic loop. Returns (response_text, accumulated_usage)."""

        # Build context with optional memory injection
        skill_context = self._skills.get_combined_system_context() if self._skills else None
        tools_schema = self._skills.get_all_tools_schema() if self._skills else []

        # Prepend extra tools (e.g. delegate_to_subagent from the orchestrator)
        if extra_tools:
            tools_schema = list(extra_tools) + tools_schema

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

        # Build persona prompt — use agent profile if available, else global persona file
        if self._profile is not None and (self._profile.persona_json or self._profile.system_prompt):
            from steelclaw.agents.persona import build_persona_prompt
            persona_prompt = build_persona_prompt(self._profile)
            effective_system = self._profile.system_prompt or self._settings.llm.system_prompt
        else:
            persona_prompt = build_persona_system_prompt()
            effective_system = self._settings.llm.system_prompt

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
            system = f"{persona_prompt}\n\n{effective_system}"
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

        # Track tool calls for self-reflection
        tool_calls_log: list[dict] = []

        # Agent loop with tool calling
        max_rounds = self._settings.max_tool_rounds
        for round_num in range(max_rounds):
            response = await self._provider.complete(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            # Accumulate usage
            model_used = response.model or model_used
            total_prompt += response.usage.get("prompt_tokens", 0)
            total_completion += response.usage.get("completion_tokens", 0)

            # If no tool calls, we have the final text response
            if not response.tool_calls:
                final_text = response.content or "(no response)"

                # Strip <think>...</think> reasoning blocks before returning
                think_blocks = _extract_think_blocks(final_text)
                if think_blocks:
                    logger.debug(
                        "Stripping %d <think> block(s) from response: %s",
                        len(think_blocks),
                        " | ".join(b[:100] for b in think_blocks),
                    )
                    final_text = _strip_think_blocks(final_text) or "(no response)"

                usage = {
                    "model": model_used,
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                }

                # Fire-and-forget reflection when threshold is met
                self._maybe_trigger_reflection(
                    tool_calls_log=tool_calls_log,
                    task_context=message.content[:200] if message.content else "",
                    session_id=session.id,
                )

                return final_text, usage

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
                skill_obj = self._skills.get_skill_for_tool(tc.name) if self._skills else None
                skill_name = skill_obj.name if skill_obj else None
                skill_label = skill_obj.metadata.description if skill_obj else None
                if on_tool_event:
                    try:
                        await on_tool_event({
                            "type": "tool_start",
                            "name": tc.name,
                            "id": tc.id,
                            "skill": skill_name,
                            "label": skill_label,
                            "arguments": tc.arguments,
                        })
                    except Exception as exc:
                        logger.debug("on_tool_event(tool_start) handler error: %s", exc, exc_info=True)
                t0 = time.monotonic()
                result = await self._execute_tool_call(tc)
                duration_ms = int((time.monotonic() - t0) * 1000)
                if on_tool_event:
                    try:
                        await on_tool_event({
                            "type": "tool_end",
                            "name": tc.name,
                            "id": tc.id,
                            "result_preview": result[:200],
                            "duration_ms": duration_ms,
                        })
                    except Exception as exc:
                        logger.debug("on_tool_event(tool_end) handler error: %s", exc, exc_info=True)
                messages.append(
                    self._context.build_tool_result_message(tc.id, result)
                )
                # Log for reflection
                tool_calls_log.append({"name": tc.name, "arguments": tc.arguments})

        # Exhausted tool rounds — still fire reflection and strip any think blocks
        final_text = response.content or "I've been working on this but reached my iteration limit. Here's what I have so far."
        final_text = _strip_think_blocks(final_text)

        self._maybe_trigger_reflection(
            tool_calls_log=tool_calls_log,
            task_context=message.content[:200] if message.content else "",
            session_id=session.id,
        )

        logger.warning("Agent exhausted %d tool rounds", max_rounds)
        usage = {
            "model": model_used,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        }
        return final_text, usage

    def _maybe_trigger_reflection(
        self,
        tool_calls_log: list[dict],
        task_context: str,
        session_id: str,
    ) -> None:
        """Fire-and-forget reflection when the tool-call threshold is met.

        Does nothing if reflection is disabled or threshold not reached.
        """
        reflection_settings = self._settings.reflection
        if not reflection_settings.enabled:
            return
        if len(tool_calls_log) < reflection_settings.threshold:
            return
        if self._skill_generator is None:
            return

        logger.info(
            "Reflection triggered: %d tool calls >= threshold %d (session %s)",
            len(tool_calls_log),
            reflection_settings.threshold,
            session_id,
        )

        async def _reflect():
            try:
                result = await self._skill_generator.reflect_and_create(
                    tool_calls_log=tool_calls_log,
                    task_context=task_context,
                    skill_auto_create=reflection_settings.skill_auto_create,
                )
                logger.info("Reflection result: %s", result.get("reason", ""))
            except Exception as exc:
                logger.warning("Reflection failed: %s", exc)

        task = asyncio.create_task(_reflect())
        # Track in both the instance set and the module-level set.
        # The instance set provides per-router visibility; the module-level set
        # allows app.py to drain tasks after the router instance is GC'd.
        self._background_tasks.add(task)
        _active_background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(_active_background_tasks.discard)

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
        extra_tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream agent response as chunks. Yields dicts:

        - {"type": "chunk", "content": "text"}  — incremental text
        - {"type": "tool_start", "name": "...", "id": "..."}  — tool call starting
        - {"type": "tool_end", "name": "...", "result_preview": "..."}  — tool call done
        - {"type": "done", "content": "full text", "usage": {...}}  — final
        - {"type": "error", "content": "..."}  — on failure
        """
        # Set security context for permission checks
        set_security_context(
            session_id=str(session.id),
            platform=message.platform,
            platform_chat_id=message.platform_chat_id,
        )
        try:
            async for event in self._stream_agent_loop(message, session, db, extra_tools=extra_tools):
                yield event
        except Exception as e:
            logger.exception("Streaming agent error for session %s", session.id)
            yield {"type": "error", "content": f"I encountered an error: {e}"}
        finally:
            clear_security_context()

    async def _stream_agent_loop(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
        extra_tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Streaming agentic loop. Yields events as chunks arrive."""

        # Build context (same as non-streaming)
        skill_context = self._skills.get_combined_system_context() if self._skills else None
        tools_schema = self._skills.get_all_tools_schema() if self._skills else []

        # Prepend extra tools (e.g. delegate_to_subagent from the orchestrator)
        if extra_tools:
            tools_schema = list(extra_tools) + tools_schema

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

        # Build persona prompt — use agent profile if available, else global persona file
        if self._profile is not None and (self._profile.persona_json or self._profile.system_prompt):
            from steelclaw.agents.persona import build_persona_prompt
            persona_prompt = build_persona_prompt(self._profile)
            effective_system = self._profile.system_prompt or self._settings.llm.system_prompt
        else:
            persona_prompt = build_persona_system_prompt()
            effective_system = self._settings.llm.system_prompt

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
            system = f"{persona_prompt}\n\n{effective_system}"
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

        max_rounds = self._settings.max_tool_rounds
        for round_num in range(max_rounds):
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
                        tool_call_buffers[idx] = {"id": "", "name": "", "arguments_str": ""}
                    buf = tool_call_buffers[idx]
                    if td.get("id"):
                        buf["id"] = td["id"]
                    if td.get("name"):
                        buf["name"] += td["name"]
                    if td.get("arguments"):
                        buf["arguments_str"] += td["arguments"]

                if chunk.model:
                    model_used = chunk.model
                if chunk.usage:
                    total_prompt += chunk.usage.get("prompt_tokens", 0)
                    total_completion += chunk.usage.get("completion_tokens", 0)

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
                # Strip any <think> blocks from the accumulated content
                clean_content = _strip_think_blocks(full_content) if full_content else "(no response)"
                usage = {
                    "model": model_used,
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                }
                yield {"type": "done", "content": clean_content, "usage": usage}
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
                # Resolve skill name and human-readable label for this tool
                skill_obj = self._skills.get_skill_for_tool(tc.name) if self._skills else None
                skill_name = skill_obj.name if skill_obj else None
                skill_label = skill_obj.metadata.description if skill_obj else None
                yield {
                    "type": "tool_start",
                    "name": tc.name,
                    "id": tc.id,
                    "skill": skill_name,
                    "label": skill_label,
                    # Include arguments so the orchestrator can extract delegation targets
                    "arguments": tc.arguments,
                }
                t0 = time.monotonic()
                result = await self._execute_tool_call(tc)
                duration_ms = int((time.monotonic() - t0) * 1000)
                messages.append(
                    self._context.build_tool_result_message(tc.id, result)
                )
                yield {
                    "type": "tool_end",
                    "name": tc.name,
                    "id": tc.id,
                    "result_preview": result[:200],
                    "duration_ms": duration_ms,
                }

        # Exhausted tool rounds
        clean_content = _strip_think_blocks(full_content) if full_content else "I've been working on this but reached my iteration limit."
        usage = {
            "model": model_used,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        }
        yield {
            "type": "done",
            "content": clean_content,
            "usage": usage,
        }

    async def _execute_tool_call(self, tc: ToolCall) -> str:
        """Execute a single tool call via the skill registry."""
        if self._skills is None:
            return f"Error: No skill registry available to execute tool '{tc.name}'"

        logger.info("Executing tool: %s(%s)", tc.name, json.dumps(tc.arguments)[:200])
        result = await self._skills.execute_tool(tc.name, tc.arguments)
        if result is None:
            result = f"Tool '{tc.name}' returned no output."
        logger.debug("Tool result for %s: %s", tc.name, str(result)[:200])
        return result
