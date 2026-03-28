"""Agent router — LLM-powered agent with tool calling, skills, and persistent context."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import Session as DBSession
from steelclaw.llm.context import ContextBuilder
from steelclaw.llm.provider import LLMProvider, LLMResponse, ToolCall
from steelclaw.pricing import calculate_cost
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings
from steelclaw.skills.registry import SkillRegistry

logger = logging.getLogger("steelclaw.agents")

# Maximum tool-call iterations to prevent infinite loops
MAX_TOOL_ROUNDS = 10


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

        # Retrieve relevant memories
        memory_context = None
        if self._memory_retriever and message.content:
            memories = self._memory_retriever.retrieve_relevant(
                query_text=message.content,
                limit=self._settings.memory.top_k,
            )
            memory_context = self._memory_retriever.format_for_prompt(memories)

        if db is not None:
            messages = await self._context.build(
                session=session,
                db=db,
                skill_context=skill_context,
                memory_context=memory_context,
                current_message=message.content,
            )
        else:
            # Fallback: no DB, just system + current message
            system = self._settings.llm.system_prompt
            if skill_context:
                system = f"{system}\n\n{skill_context}"
            if memory_context:
                system = f"{system}\n\n{memory_context}"
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": message.content},
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

    async def _execute_tool_call(self, tc: ToolCall) -> str:
        """Execute a single tool call via the skill registry."""
        if self._skills is None:
            return f"Error: No skill registry available to execute tool '{tc.name}'"

        logger.info("Executing tool: %s(%s)", tc.name, json.dumps(tc.arguments)[:200])
        result = await self._skills.execute_tool(tc.name, tc.arguments)
        logger.debug("Tool result: %s", result[:500])
        return result
