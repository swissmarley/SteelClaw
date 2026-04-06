"""Multi-agent orchestrator — hierarchical delegation from main agent to sub-agents."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.agents.router import AgentResponse, AgentRouter
from steelclaw.db.models import AgentProfile
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import AgentSettings

logger = logging.getLogger("steelclaw.orchestrator")

# ---------------------------------------------------------------------------
# Tool schemas injected into the main agent
# ---------------------------------------------------------------------------

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

_LIST_SUBAGENTS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "list_subagents",
        "description": (
            "List all sub-agents with their names, display names, models, "
            "active status, and system prompts. Use this to see what sub-agents "
            "are available before delegating or managing them."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

_CREATE_SUBAGENT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "create_subagent",
        "description": (
            "Create a new sub-agent with a custom name, system prompt, and optional model override. "
            "The sub-agent will be immediately available for delegation once created."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Unique identifier name for the sub-agent. "
                        "Use lowercase with hyphens or underscores, no spaces (e.g. research-agent)."
                    ),
                },
                "display_name": {
                    "type": "string",
                    "description": "Human-readable display name (e.g. 'Research Agent').",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "System prompt defining the sub-agent's role, expertise, and behaviour.",
                },
                "model_override": {
                    "type": "string",
                    "description": (
                        "Optional LLM model to use for this sub-agent "
                        "(e.g. gpt-4o, claude-opus-4-5, deepseek/deepseek-chat). "
                        "Leave empty to use the default model."
                    ),
                },
            },
            "required": ["name", "system_prompt"],
        },
    },
}

_UPDATE_SUBAGENT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "update_subagent",
        "description": (
            "Update an existing sub-agent's configuration: display name, system prompt, "
            "model override, or active status. Only supply the fields you want to change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the sub-agent to update.",
                },
                "display_name": {
                    "type": "string",
                    "description": "New human-readable display name.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "New system prompt for the sub-agent.",
                },
                "model_override": {
                    "type": "string",
                    "description": "New LLM model override (empty string to reset to default).",
                },
                "is_active": {
                    "type": "boolean",
                    "description": "Set false to deactivate or true to reactivate the sub-agent.",
                },
            },
            "required": ["agent_name"],
        },
    },
}

_DELETE_SUBAGENT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "delete_subagent",
        "description": (
            "Permanently delete a sub-agent. This action cannot be undone. "
            "The main agent cannot be deleted."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the sub-agent to delete.",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Must be set to true to confirm the deletion.",
                },
            },
            "required": ["agent_name", "confirm"],
        },
    },
}

# Always-present agent management tools (available even with no sub-agents)
_AGENT_MGMT_TOOLS: list[dict] = [
    _LIST_SUBAGENTS_TOOL,
    _CREATE_SUBAGENT_TOOL,
    _UPDATE_SUBAGENT_TOOL,
    _DELETE_SUBAGENT_TOOL,
]

# Tool names handled internally by the orchestrator (never forwarded to skills)
_ORCHESTRATOR_TOOLS: frozenset[str] = frozenset({
    "delegate_to_subagent",
    "list_subagents",
    "create_subagent",
    "update_subagent",
    "delete_subagent",
})


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
    2. Build the delegation + agent management tool schemas and inject them into
       the main agent's tool list.
    3. Run the main agent loop with those tools injected.
    4. When the main agent calls ``delegate_to_subagent``, intercept the tool
       call, spin up a sub-agent ``AgentRouter``, run the task, and return the
       result back to the main agent as a tool result.
    5. When the main agent calls any agent management tool (list/create/update/
       delete_subagent), execute the operation directly against the database.
    6. Sub-agents never interact with the user directly.
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

        orchestrator = self
        original_exec = main_router._execute_tool_call

        async def _patched_execute(tc):
            return await orchestrator._dispatch_orchestrator_tool(
                tc, db, original_exec
            )

        main_router._execute_tool_call = _patched_execute

        # Wrap on_tool_event to enrich delegation events with the real agent name.
        wrapped_on_tool_event = on_tool_event
        if on_tool_event is not None:
            _delegation_map: dict[str, str] = {}

            async def _enriched_on_tool_event(event: dict) -> None:
                event = MultiAgentOrchestrator._enrich_delegation_event(event, _delegation_map)
                await on_tool_event(event)

            wrapped_on_tool_event = _enriched_on_tool_event

        try:
            return await main_router.route_with_usage(
                message,
                session,
                db=db,
                on_tool_event=wrapped_on_tool_event,
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
        """Stream the main agent's response.

        Delegation events are enriched so the UI shows which sub-agent is
        being called (e.g. ``delegate_to_research-agent``) rather than the
        generic ``delegate_to_subagent`` tool name.
        """
        main_router = await self._build_main_router(db)
        extra_tools = await self._build_extra_tools(db)

        orchestrator = self
        original_exec = main_router._execute_tool_call

        async def _patched_execute(tc):
            return await orchestrator._dispatch_orchestrator_tool(
                tc, db, original_exec
            )

        main_router._execute_tool_call = _patched_execute

        # Track call_id → agent_name for transforming tool_end events
        delegation_map: dict[str, str] = {}

        try:
            async for event in main_router.stream_response(
                message, session, db=db, extra_tools=extra_tools
            ):
                event = MultiAgentOrchestrator._enrich_delegation_event(event, delegation_map)
                yield event
        finally:
            main_router._execute_tool_call = original_exec

    @staticmethod
    def _enrich_delegation_event(event: dict, delegation_map: dict) -> dict:
        """Transform a raw 'delegate_to_subagent' event to include the real agent name.

        Mutates *delegation_map* as a side-effect (stores/pops call_id → agent_name).
        Returns the (possibly replaced) event dict.
        """
        etype = event.get("type", "")
        if etype == "tool_start" and event.get("name") == "delegate_to_subagent":
            args = event.get("arguments", {})
            agent_name = args.get("agent_name", "subagent")
            call_id = event.get("id") or "delegate_to_subagent"
            delegation_map[call_id] = agent_name
            return {
                **event,
                "name": f"delegate_to_{agent_name}",
                "label": f"Delegating to {agent_name}",
                "subagent": agent_name,
            }
        if etype == "tool_end" and event.get("name") == "delegate_to_subagent":
            call_id = event.get("id") or "delegate_to_subagent"
            agent_name = delegation_map.pop(call_id, "subagent")
            return {
                **event,
                "name": f"delegate_to_{agent_name}",
                "subagent": agent_name,
            }
        return event

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
        """Return agent management tools + delegation tool (when sub-agents exist)."""
        extra: list[dict] = list(_AGENT_MGMT_TOOLS)

        if db is None:
            return extra

        stmt = select(AgentProfile).where(
            AgentProfile.is_main.is_(False),
            AgentProfile.is_active.is_(True),
        )
        result = await db.execute(stmt)
        sub_agents = result.scalars().all()

        if sub_agents:
            tool = json.loads(json.dumps(_DELEGATE_TOOL_SCHEMA))
            names = ", ".join(a.name for a in sub_agents)
            tool["function"]["description"] += f" Available sub-agents: {names}."
            # Delegation tool goes first so LLM sees it prominently
            extra = [tool] + extra

        return extra

    async def _dispatch_orchestrator_tool(self, tc, db, original_exec) -> str:
        """Route a tool call to the correct orchestrator handler or skill registry."""
        if tc.name == "delegate_to_subagent":
            return await self._execute_delegation(tc.arguments, db)
        if tc.name == "list_subagents":
            return await self._execute_list_subagents(db)
        if tc.name == "create_subagent":
            return await self._execute_create_subagent(tc.arguments, db)
        if tc.name == "update_subagent":
            return await self._execute_update_subagent(tc.arguments, db)
        if tc.name == "delete_subagent":
            return await self._execute_delete_subagent(tc.arguments, db)
        return await original_exec(tc)

    # ── Delegation ──────────────────────────────────────────────────────

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

        stmt = select(AgentProfile).where(
            AgentProfile.name == agent_name,
            AgentProfile.is_active.is_(True),
        )
        result = await db.execute(stmt)
        profile: Optional[AgentProfile] = result.scalar_one_or_none()

        if profile is None:
            # Give useful feedback: list what agents ARE available
            available_stmt = select(AgentProfile).where(
                AgentProfile.is_main.is_(False),
                AgentProfile.is_active.is_(True),
            )
            avail_result = await db.execute(available_stmt)
            available = [a.name for a in avail_result.scalars().all()]
            hint = f" Available sub-agents: {', '.join(available)}." if available else " No sub-agents exist yet — use create_subagent to create one."
            return f"Error: sub-agent '{agent_name}' not found or inactive.{hint}"

        if profile.is_main:
            return "Error: cannot delegate to the main agent."

        logger.info("Delegating to sub-agent '%s': %.100s", agent_name, task)

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
        # Use a fake session whose ID won't match any real session — the
        # context builder will return empty history (clean slate for the task).
        fake_session = _FakeSession(agent_name=agent_name, agent_id=profile.id)

        try:
            # Pass db so the sub-agent's skills have DB access; the fake
            # session ID ensures no real conversation history is loaded.
            response = await sub_router.route_with_usage(
                synthetic_msg, fake_session, db=db
            )
            content = response.outbound.content
            logger.info("Sub-agent '%s' returned: %.100s", agent_name, content)
            return content
        except Exception as exc:
            logger.exception("Sub-agent '%s' raised an error", agent_name)
            return f"Sub-agent '{agent_name}' encountered an error: {exc}"

    # ── Agent management tools ──────────────────────────────────────────

    async def _execute_list_subagents(self, db: AsyncSession | None) -> str:
        """List all sub-agents with their current configuration."""
        if db is None:
            return "Error: database not available."

        stmt = select(AgentProfile).where(
            AgentProfile.is_main.is_(False)
        ).order_by(AgentProfile.name)
        result = await db.execute(stmt)
        agents = result.scalars().all()

        if not agents:
            return (
                "No sub-agents exist yet. "
                "Use the create_subagent tool to create your first sub-agent."
            )

        lines = [f"Sub-agents ({len(agents)} total):"]
        for a in agents:
            status = "active" if a.is_active else "inactive"
            model = a.model_override or "default"
            lines.append(f"\n• {a.name}  [{status}]")
            lines.append(f"  Display name: {a.display_name}")
            lines.append(f"  Model: {model}")
            if a.system_prompt:
                preview = a.system_prompt[:120].replace("\n", " ")
                lines.append(f"  Prompt: {preview}{'...' if len(a.system_prompt) > 120 else ''}")
        return "\n".join(lines)

    async def _execute_create_subagent(
        self, arguments: dict, db: AsyncSession | None
    ) -> str:
        """Create a new sub-agent."""
        if db is None:
            return "Error: database not available."

        raw_name: str = arguments.get("name", "").strip()
        if not raw_name:
            return "Error: name is required."

        # Normalise: lowercase, spaces → hyphens
        name = raw_name.lower().replace(" ", "-")

        if name == "main":
            return "Error: 'main' is reserved for the system main agent."

        system_prompt: str = arguments.get("system_prompt", "").strip()
        if not system_prompt:
            return "Error: system_prompt is required."

        existing = await db.execute(
            select(AgentProfile).where(AgentProfile.name == name)
        )
        if existing.scalar_one_or_none():
            return f"Error: a sub-agent named '{name}' already exists. Use update_subagent to modify it."

        model_override = arguments.get("model_override") or None
        display_name = arguments.get("display_name") or name.replace("-", " ").replace("_", " ").title()

        agent = AgentProfile(
            name=name,
            display_name=display_name,
            system_prompt=system_prompt,
            model_override=model_override,
            is_main=False,
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        logger.info("Created sub-agent '%s' (model=%s)", name, model_override or "default")
        return (
            f"Sub-agent '{name}' created successfully.\n"
            f"Display name: {display_name}\n"
            f"Model: {model_override or 'default'}\n"
            f"You can now delegate tasks to it using delegate_to_subagent."
        )

    async def _execute_update_subagent(
        self, arguments: dict, db: AsyncSession | None
    ) -> str:
        """Update an existing sub-agent."""
        if db is None:
            return "Error: database not available."

        agent_name: str = arguments.get("agent_name", "").strip()
        if not agent_name:
            return "Error: agent_name is required."

        stmt = select(AgentProfile).where(AgentProfile.name == agent_name)
        result = await db.execute(stmt)
        agent: Optional[AgentProfile] = result.scalar_one_or_none()

        if agent is None:
            return f"Error: sub-agent '{agent_name}' not found."
        if agent.is_main:
            return "Error: the main agent cannot be modified via this tool."

        changes: list[str] = []
        if "display_name" in arguments and arguments["display_name"] is not None:
            agent.display_name = arguments["display_name"]
            changes.append(f"display_name → {agent.display_name}")
        if "system_prompt" in arguments and arguments["system_prompt"] is not None:
            agent.system_prompt = arguments["system_prompt"]
            changes.append("system_prompt updated")
        if "model_override" in arguments:
            val = arguments["model_override"]
            agent.model_override = val or None
            changes.append(f"model_override → {val or 'default'}")
        if "is_active" in arguments and arguments["is_active"] is not None:
            agent.is_active = bool(arguments["is_active"])
            changes.append(f"is_active → {agent.is_active}")

        if not changes:
            return "No changes provided — nothing was updated."

        agent.updated_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("Updated sub-agent '%s': %s", agent_name, ", ".join(changes))
        return f"Sub-agent '{agent_name}' updated:\n" + "\n".join(f"  • {c}" for c in changes)

    async def _execute_delete_subagent(
        self, arguments: dict, db: AsyncSession | None
    ) -> str:
        """Delete a sub-agent."""
        if db is None:
            return "Error: database not available."

        agent_name: str = arguments.get("agent_name", "").strip()
        confirm: bool = bool(arguments.get("confirm", False))

        if not agent_name:
            return "Error: agent_name is required."
        if not confirm:
            return (
                f"Deletion not confirmed. "
                f"Call delete_subagent again with confirm=true to permanently delete '{agent_name}'."
            )

        stmt = select(AgentProfile).where(AgentProfile.name == agent_name)
        result = await db.execute(stmt)
        agent: Optional[AgentProfile] = result.scalar_one_or_none()

        if agent is None:
            return f"Error: sub-agent '{agent_name}' not found."
        if agent.is_main:
            return "Error: the main agent cannot be deleted."

        await db.delete(agent)
        await db.commit()

        logger.info("Deleted sub-agent '%s'", agent_name)
        return f"Sub-agent '{agent_name}' has been permanently deleted."
