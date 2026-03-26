"""Agent router — LLM-powered agent with tool calling, skills, and persistent context."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import Session as DBSession
from steelclaw.llm.context import ContextBuilder
from steelclaw.llm.provider import LLMProvider, LLMResponse, ToolCall
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings
from steelclaw.skills.registry import SkillRegistry

logger = logging.getLogger("steelclaw.agents")

# Maximum tool-call iterations to prevent infinite loops
MAX_TOOL_ROUNDS = 10


class AgentRouter:
    """Routes messages to the LLM with tool-calling support.

    Pipeline:
    1. Build conversation context from DB history + skill system prompts
    2. Call LLM with available tools from loaded skills
    3. If LLM returns tool calls → execute tools → feed results back → repeat
    4. Return final text response
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

    async def route(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> OutboundMessage:
        """Process a message through the LLM agent pipeline."""
        try:
            response_text = await self._run_agent_loop(message, session, db)
        except Exception as e:
            logger.exception("Agent error for session %s", session.id)
            response_text = f"I encountered an error: {e}"

        return OutboundMessage(
            platform=message.platform,
            platform_chat_id=message.platform_chat_id,
            content=response_text,
            reply_to_message_id=message.platform_message_id,
        )

    async def _run_agent_loop(
        self,
        message: InboundMessage,
        session: DBSession,
        db: AsyncSession | None = None,
    ) -> str:
        """Run the agentic loop: LLM call → tool execution → repeat until text response."""

        # Build context
        skill_context = self._skills.get_combined_system_context() if self._skills else None
        tools_schema = self._skills.get_all_tools_schema() if self._skills else []

        if db is not None:
            messages = await self._context.build(
                session=session,
                db=db,
                skill_context=skill_context,
                current_message=message.content,
            )
        else:
            # Fallback: no DB, just system + current message
            system = self._settings.llm.system_prompt
            if skill_context:
                system = f"{system}\n\n{skill_context}"
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": message.content},
            ]

        # Agent loop with tool calling
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self._provider.complete(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            # If no tool calls, return the text response
            if not response.tool_calls:
                return response.content or "(no response)"

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
        return response.content or "I've been working on this but reached my iteration limit. Here's what I have so far."

    async def _execute_tool_call(self, tc: ToolCall) -> str:
        """Execute a single tool call via the skill registry."""
        if self._skills is None:
            return f"Error: No skill registry available to execute tool '{tc.name}'"

        logger.info("Executing tool: %s(%s)", tc.name, json.dumps(tc.arguments)[:200])
        result = await self._skills.execute_tool(tc.name, tc.arguments)
        logger.debug("Tool result: %s", result[:500])
        return result
