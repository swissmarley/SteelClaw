"""Multi-agent orchestrator — hierarchical delegation from main agent to sub-agents."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.agents.router import AgentResponse, AgentRouter
from steelclaw.db.models import AgentProfile
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings

logger = logging.getLogger("steelclaw.orchestrator")

# Tool schema injected into the main agent so it can delegate work to sub-agents
_DELEGATE_TOOL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "delegate_to_subagent",
        "description": (
            "Delegate a specialised task to a sub-agent worker. "
            "Use this when a task requires dedicated expertise from a specific sub-agent. "
            "The sub-agent executes the task independently and returns its result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "The name of the sub-agent to delegate the task to.",
                },
                "task": {
                    "type": "string",
                    "description": "A clear description of the task to be executed by the sub-agent.",
                },
            },
            "required": ["agent_name", "task"],
        },
    },
}


class _FakeSession:
    """Minimal session-like object used when running sub-agents without DB persistence."""

    def __init__(self, agent_name: str, agent_id: str) -> None:
        self.id = f"subagent_{agent_name}"
        self.unified_session_id = f"subagent_{agent_name}"
        self.agent_id = agent_id


class MultiAgentOrchestrator:
    """Hierarchical multi-agent orchestrator.

    Exposes the same public interface as ``AgentRouter`` so it can replace it
    transparently in ``gateway/router.py``.

    Routing pipeline:
    1. Load the main ``AgentProfile`` (``is_main=True``) from the database.
    2. Build the delegation tool schema listing available sub-agents.
    3. Run the main agent loop with the delegation tool injected.
    4. When the main agent calls ``delegate_to_subagent``, intercept the tool
       call, spin up a sub-agent ``AgentRouter``, run the task, and return the
       result back to the main agent as a tool result.
    5. Sub-agents never interact with the user directly.
    """

    def __init__(
        self,
        settings: AgentSettings,
        skill_registry=None,
    ) -> None:
        self._settings = settings
        self._skills = skill_registry
        self._memory_retriever = None
        self._memory_ingestor = None

    def set_memory(self, retriever, ingestor) -> None:
        """Inject memory components after initialisation (mirrors AgentRouter API)."""
        self._memory_retriever = retriever
        self._memory_ingestor = ingestor

    # ── Public interface (mirrors AgentRouter) ──────────────────────────

    async def route(
        self,
        message: InboundMessage,
        session,
        db: AsyncSession | None = None,
    ) -> OutboundMessage:
        result = await self.route_with_usage(message, session, db)
        return result.outbound

    async def route_with_usage(
        self,
        message: InboundMessage,
        session,
        db: AsyncSession | None = None,
        on_tool_event=None,
    ) -> AgentResponse:
        """Route a message through the main agent, handling sub-agent delegation."""
        main_router = await self._build_main_router(db)
        extra_tools = await self._build_extra_tools(db)

        # Patch the router's _execute_tool_call to intercept delegation calls
        original_exec = main_router._execute_tool_call
        orchestrator = self

        async def _patched_execute(tc):
            if tc.name == "delegate_to_subagent":
                return await orchestrator._execute_delegation(tc.arguments, db)
            return await original_exec(tc)

        main_router._execute_tool_call = _patched_execute
        try:
            return await main_router.route_with_usage(
                message,
                session,
                db=db,
                on_tool_event=on_tool_event,
                extra_tools=extra_tools,
            )
        finally:
            main_router._execute_tool_call = original_exec

    async def stream_response(
        self,
        message: InboundMessage,
        session,
        db: AsyncSession | None = None,
    ) -> AsyncIterator[dict]:
        """Stream the main agent's response; delegation tool results appear as tool_end events."""
        main_router = await self._build_main_router(db)
        extra_tools = await self._build_extra_tools(db)

        orchestrator = self
        original_exec = main_router._execute_tool_call

        async def _patched_execute(tc):
            if tc.name == "delegate_to_subagent":
                return await orchestrator._execute_delegation(tc.arguments, db)
            return await original_exec(tc)

        main_router._execute_tool_call = _patched_execute
        try:
            async for event in main_router.stream_response(
                message, session, db=db, extra_tools=extra_tools
            ):
                yield event
        finally:
            main_router._execute_tool_call = original_exec

    # ── Internal helpers ────────────────────────────────────────────────

    async def _build_main_router(self, db: AsyncSession | None) -> AgentRouter:
        """Construct an AgentRouter for the main agent profile."""
        profile: Optional[AgentProfile] = None
        if db is not None:
            stmt = select(AgentProfile).where(AgentProfile.is_main.is_(True))
            result = await db.execute(stmt)
            profile = result.scalar_one_or_none()

        router = AgentRouter(
            settings=self._settings,
            skill_registry=self._skills,
            agent_profile=profile,
        )
        router.set_memory(self._memory_retriever, self._memory_ingestor)
        return router

    async def _build_extra_tools(self, db: AsyncSession | None) -> list[dict]:
        """Return the delegation tool schema if any active sub-agents exist."""
        if db is None:
            return []

        stmt = select(AgentProfile).where(
            AgentProfile.is_main.is_(False),
            AgentProfile.is_active.is_(True),
        )
        result = await db.execute(stmt)
        sub_agents = result.scalars().all()
        if not sub_agents:
            return []

        # Deep-copy and enhance with available agent names
        tool = json.loads(json.dumps(_DELEGATE_TOOL_SCHEMA))
        names = ", ".join(a.name for a in sub_agents)
        tool["function"]["description"] += f" Available sub-agents: {names}."
        return [tool]

    async def _execute_delegation(
        self,
        arguments: dict,
        db: AsyncSession | None,
    ) -> str:
        """Run a task through the named sub-agent and return its text response."""
        agent_name: str = arguments.get("agent_name", "")
        task: str = arguments.get("task", "")

        if not agent_name or not task:
            return "Error: both agent_name and task are required for delegation."

        if db is None:
            return (
                f"Error: no database session available to load sub-agent '{agent_name}'."
            )

        # Load the sub-agent profile
        stmt = select(AgentProfile).where(
            AgentProfile.name == agent_name,
            AgentProfile.is_active.is_(True),
        )
        result = await db.execute(stmt)
        profile: Optional[AgentProfile] = result.scalar_one_or_none()

        if profile is None:
            return f"Error: sub-agent '{agent_name}' not found or is inactive."
        if profile.is_main:
            return "Error: cannot delegate to the main agent."

        logger.info(
            "Delegating to sub-agent '%s': %.100s", agent_name, task
        )

        sub_router = AgentRouter(
            settings=self._settings,
            skill_registry=self._skills,
            agent_profile=profile,
        )
        sub_router.set_memory(self._memory_retriever, self._memory_ingestor)

        synthetic_msg = InboundMessage(
            platform="internal",
            platform_chat_id=f"subagent_{agent_name}",
            platform_user_id="orchestrator",
            content=task,
        )
        fake_session = _FakeSession(agent_name=agent_name, agent_id=profile.id)

        try:
            # Run without DB so sub-agent history doesn't pollute the main conversation
            response = await sub_router.route_with_usage(
                synthetic_msg, fake_session, db=None
            )
            logger.info(
                "Sub-agent '%s' returned %.100s", agent_name, response.outbound.content
            )
            return response.outbound.content
        except Exception as exc:
            logger.exception("Sub-agent '%s' raised an error", agent_name)
            return f"Sub-agent '{agent_name}' encountered an error: {exc}"
