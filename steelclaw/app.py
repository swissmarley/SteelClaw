"""FastAPI application factory with async lifespan."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from steelclaw.db.engine import create_tables, dispose_engine, init_engine
from steelclaw.gateway.registry import ConnectorRegistry
from steelclaw.settings import Settings

logger = logging.getLogger("steelclaw")


def _create_memory_store(memory_settings):
    """Factory: returns the configured memory backend (VectorStore or VikingStore)."""
    if memory_settings.backend == "openviking":
        from steelclaw.memory.viking_store import VikingStore
        return VikingStore(memory_settings)
    from steelclaw.memory.vector_store import VectorStore
    return VectorStore(memory_settings)


async def _start_openviking_server(memory_settings) -> "OpenVikingManager | None":
    """Start OpenViking server if configured and auto-start enabled."""
    if memory_settings.backend != "openviking":
        return None
    if not memory_settings.openviking_auto_start:
        return None

    from steelclaw.memory.openviking_manager import OpenVikingManager

    manager = OpenVikingManager(memory_settings)
    if await manager.start():
        return manager
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    from steelclaw.paths import resolve_path

    settings: Settings = app.state.settings

    # Resolve relative database path against project root
    db_url = settings.database.url
    if ":///" in db_url:
        prefix, db_rel = db_url.split(":///", 1)
        db_path = resolve_path(db_rel)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"{prefix}:///{db_path}"
        settings.database.url = db_url

    # ── Database ────────────────────────────────────────────────────────
    init_engine(settings.database.url, echo=settings.database.echo)
    await create_tables()
    logger.info("Database initialised")

    # ── Tool system ────────────────────────────────────────────────────
    from steelclaw.skills.registry import ToolRegistry

    # Resolve relative skill paths against project root
    tool_settings = settings.agents.tools
    tool_settings.bundled_dir = str(resolve_path(tool_settings.bundled_dir))
    tool_settings.global_dir = str(resolve_path(tool_settings.global_dir))
    tool_settings.workspace_dir = str(resolve_path(tool_settings.workspace_dir))

    tool_registry = ToolRegistry(tool_settings)
    tool_registry.load_all()

    # Verify critical tools loaded
    for critical in ("web_search",):
        if tool_registry.get_skill(critical) is None:
            logger.warning("Critical tool '%s' failed to load — agent may lack web access", critical)
        else:
            logger.info("Critical tool '%s' loaded OK", critical)

    app.state.tool_registry = tool_registry
    app.state.skill_registry = tool_registry  # backward-compatible alias

    # ── Skills system (Phase 2 — Claude-compatible skills) ──────────────
    from steelclaw.skills.skill_manager import SkillManager

    skill_settings = settings.agents.skills
    skill_settings.bundled_dir = str(resolve_path(skill_settings.bundled_dir))
    skill_settings.global_dir = str(resolve_path(skill_settings.global_dir))
    skill_settings.workspace_dir = str(resolve_path(skill_settings.workspace_dir))

    skill_manager = SkillManager(
        bundled_dir=skill_settings.bundled_dir,
        global_dir=skill_settings.global_dir,
        workspace_dir=skill_settings.workspace_dir,
        enabled=skill_settings.enabled,
        disabled_skills=skill_settings.disabled_skills,
        enabled_skills=skill_settings.enabled_skills,
    )
    skill_manager.load_all()
    app.state.skill_manager = skill_manager

    # ── Security ────────────────────────────────────────────────────────
    from steelclaw.security.extended_permissions import CapabilityPermissions
    from steelclaw.security.permissions import PermissionManager
    from steelclaw.security.sandbox import set_permission_manager, set_sudo_manager

    # Resolve approvals file path
    settings.agents.security.approvals_file = str(
        resolve_path(settings.agents.security.approvals_file)
    )

    # Load capability permissions from ~/.steelclaw/permissions.yaml
    ext_perm_settings = settings.agents.security.extended_permissions
    capability_permissions = CapabilityPermissions.load(
        path=ext_perm_settings.permissions_file,
        auto_create=ext_perm_settings.auto_create_file,
    )

    permission_manager = PermissionManager(settings.agents.security, capability_permissions)
    set_permission_manager(permission_manager)
    app.state.permission_manager = permission_manager
    app.state.capability_permissions = capability_permissions

    # Initialise sudo manager if enabled
    sudo_settings = settings.agents.security.sudo
    if sudo_settings.enabled:
        from steelclaw.security.sudo_manager import SudoManager
        sudo_manager = SudoManager(sudo_settings)
        set_sudo_manager(sudo_manager)
        app.state.sudo_manager = sudo_manager
        logger.info(
            "Sudo support enabled (audit log: %s, whitelist: %d pattern(s))",
            sudo_settings.audit_log,
            len(sudo_settings.whitelist),
        )
    else:
        logger.info("Sudo support disabled (set agents.security.sudo.enabled=true to enable)")

    # ── Memory system ────────────────────────────────────────────────────
    from steelclaw.memory.ingestion import MemoryIngestor
    from steelclaw.memory.retrieval import MemoryRetriever

    # Start OpenViking server if configured
    openviking_manager = await _start_openviking_server(settings.agents.memory)
    app.state.openviking_manager = openviking_manager

    vector_store = _create_memory_store(settings.agents.memory)
    memory_retriever = MemoryRetriever(vector_store)
    memory_ingestor = MemoryIngestor(vector_store)
    app.state.vector_store = vector_store
    app.state.memory_retriever = memory_retriever
    app.state.memory_ingestor = memory_ingestor

    # ── SQLite FTS5 memory (optional fast keyword search) ────────────────
    fts_store = None
    fts_settings = settings.agents.memory_fts
    if fts_settings.enabled:
        from steelclaw.memory.sqlite_fts import FTSMemoryStore
        fts_store = FTSMemoryStore(fts_settings.db_path)
        await fts_store.init()
        app.state.fts_store = fts_store
        logger.info("SQLite FTS5 memory store enabled at %s", fts_settings.db_path)

    # ── Agent router (LLM-powered multi-agent orchestrator) ────────────
    from steelclaw.agents.orchestrator import MultiAgentOrchestrator
    from steelclaw.gateway.router import set_agent_router, set_memory_ingestor

    orchestrator = MultiAgentOrchestrator(
        settings=settings.agents,
        tool_registry=tool_registry,
        skill_manager=skill_manager,
    )
    orchestrator.set_memory(memory_retriever, memory_ingestor)

    # ── Tool generator for autonomous tool creation ────────────────────
    if settings.agents.reflection.enabled:
        from steelclaw.skills.generator import SkillGenerator
        from steelclaw.llm.provider import LLMProvider

        _gen_provider = LLMProvider(settings.agents.llm)
        global_dir = Path(settings.agents.tools.global_dir)
        tool_generator = SkillGenerator(_gen_provider, global_dir, tool_registry)
        orchestrator.set_tool_generator(tool_generator)
        app.state.tool_generator = tool_generator
        app.state.skill_generator = tool_generator  # backward-compatible alias
        logger.info(
            "Autonomous tool generator enabled (threshold=%d, auto_create=%s)",
            settings.agents.reflection.threshold,
            settings.agents.reflection.tool_auto_create,
        )

    # Inject tool registry + skill manager into skill_manager bundled tool
    _inject_skill_manager(tool_registry, settings.agents.tools, skill_manager)
    set_agent_router(orchestrator)
    set_memory_ingestor(memory_ingestor)
    app.state.agent_router = orchestrator

    # ── Ensure main agent exists ────────────────────────────────────────
    await _ensure_main_agent(settings)

    # ── Task scheduler ──────────────────────────────────────────────────
    from steelclaw.scheduler.engine import TaskEngine

    task_engine = TaskEngine(settings.agents.scheduler)
    task_engine.start()
    app.state.task_engine = task_engine

    # Inject into the dynamically-loaded cron_manager module (same pattern
    # as skill_manager — the loader registers it as steelclaw_skill_cron_manager)
    _cron_mod = sys.modules.get("steelclaw_skill_cron_manager")
    if _cron_mod and hasattr(_cron_mod, "set_task_engine"):
        _cron_mod.set_task_engine(task_engine)
    else:
        from steelclaw.skills.bundled.cron_manager import set_task_engine
        set_task_engine(task_engine)

    # ── Session heartbeat ───────────────────────────────────────────────
    from steelclaw.session_heartbeat import run_heartbeat

    lifecycle = settings.agents.session_lifecycle
    task_engine.add_interval_job(
        job_id="session_heartbeat",
        func=run_heartbeat,
        seconds=lifecycle.heartbeat_interval_seconds,
        kwargs={"lifecycle_settings": lifecycle},
    )

    # ── Messaging gateway ───────────────────────────────────────────────
    from steelclaw.gateway.router import process_message, set_connector_registry

    registry = ConnectorRegistry(settings.gateway)

    async def _connector_handler(inbound):
        """Handle messages from platform connectors (Telegram, Discord, etc.)."""
        from steelclaw.db.engine import get_async_session

        connector = registry.get(inbound.platform)
        chat_id = inbound.platform_chat_id

        # Start typing indicator while processing
        if connector:
            await connector.start_typing(chat_id)

        async def _on_tool_event(event: dict) -> None:
            """Forward tool_start/tool_end events to the connector as status messages."""
            if connector is None:
                return
            etype = event.get("type")
            if etype == "tool_start":
                await connector.send_tool_status(
                    chat_id=chat_id,
                    tool_name=event.get("name", "tool"),
                    call_id=event.get("id", event.get("name", "")),
                    label=event.get("label"),
                )
            elif etype == "tool_end":
                await connector.clear_tool_status(
                    chat_id=chat_id,
                    call_id=event.get("id", event.get("name", "")),
                )

        outbound = None
        try:
            async for db in get_async_session():
                outbound = await process_message(
                    inbound, settings.gateway, db, on_tool_event=_on_tool_event
                )
        except Exception:
            logger.exception("Error processing connector message (%s)", inbound.platform)
        finally:
            # Stop typing indicator
            if connector:
                connector.stop_typing(chat_id)

        if outbound and connector:
            await connector.send(outbound)

    registry.set_handler(_connector_handler)
    await registry.start_all()
    set_connector_registry(registry)
    app.state.registry = registry

    # ── Permission broadcaster ─────────────────────────────────────────────
    from steelclaw.security.broadcaster import PermissionBroadcaster, set_broadcaster

    permission_broadcaster = PermissionBroadcaster(
        timeout_seconds=settings.agents.security.permission_timeout
    )
    permission_broadcaster.set_connector_registry(registry)
    set_broadcaster(permission_broadcaster)
    permission_manager.set_broadcaster(permission_broadcaster)
    # Connect broadcaster to sudo manager for interactive sudo approval
    sudo_manager = getattr(app.state, "sudo_manager", None)
    if sudo_manager:
        sudo_manager.set_broadcaster(permission_broadcaster)
    app.state.permission_broadcaster = permission_broadcaster

    logger.info("SteelClaw started on %s:%s", settings.server.host, settings.server.port)
    yield

    # ── Shutdown ────────────────────────────────────────────────────────
    task_engine.stop()
    await registry.stop_all()

    # Drain in-progress reflection background tasks before closing resources
    # so that skill-file writes and ReflectionLog entries can complete cleanly.
    from steelclaw.agents.router import drain_background_tasks
    await drain_background_tasks(timeout=10.0)

    await dispose_engine()

    # Stop OpenViking server if we started it
    if hasattr(app.state, "openviking_manager") and app.state.openviking_manager:
        await app.state.openviking_manager.stop()

    # Close FTS5 memory store
    if hasattr(app.state, "fts_store") and app.state.fts_store:
        await app.state.fts_store.close()

    logger.info("SteelClaw shut down")


def _inject_skill_manager(tool_registry, tool_settings, skill_manager=None) -> None:
    """Inject the live tool registry and skill manager into the skill_manager bundled tool.

    The dynamic skill loader registers the module under the name
    ``steelclaw_skill_skill_manager`` in ``sys.modules``, which is a
    *different* object from the package-path import
    ``steelclaw.skills.bundled.skill_manager``.  We must inject into the
    dynamically-loaded instance so that the actual tool executors see the
    registry.
    """
    try:
        module = sys.modules.get("steelclaw_skill_skill_manager")
        if module is None:
            # Fallback: maybe the loader hasn't run yet or used a different name
            from steelclaw.skills.bundled.skill_manager import _set_registry
            _set_registry(
                tool_registry,
                global_dir=tool_settings.global_dir,
                workspace_dir=tool_settings.workspace_dir,
                skill_manager=skill_manager,
            )
        else:
            module._set_registry(
                tool_registry,
                global_dir=tool_settings.global_dir,
                workspace_dir=tool_settings.workspace_dir,
                skill_manager=skill_manager,
            )
        logger.debug("Tool manager registry injected")
    except Exception as exc:
        logger.debug("Could not inject skill manager registry: %s", exc)


async def _ensure_main_agent(settings: Settings) -> None:
    """Create the main agent profile if it doesn't exist yet.

    Handles the case where an agent named 'main' already exists without
    is_main=True (e.g. created by the user) by promoting it instead of
    trying to INSERT a duplicate name, which would crash on the unique constraint.
    """
    from sqlalchemy import select

    from steelclaw.db.engine import get_async_session
    from steelclaw.db.models import AgentProfile

    async for db in get_async_session():
        # Check whether a main agent already exists
        stmt = select(AgentProfile).where(AgentProfile.is_main.is_(True))
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            return  # Already set up

        # Try to find an agent named "main" and promote it
        stmt2 = select(AgentProfile).where(AgentProfile.name == "main")
        result2 = await db.execute(stmt2)
        existing = result2.scalar_one_or_none()
        if existing:
            existing.is_main = True
            await db.commit()
            logger.info("Promoted existing 'main' agent to main agent")
        else:
            main_agent = AgentProfile(
                name="main",
                display_name="SteelClaw",
                is_main=True,
                system_prompt=settings.agents.llm.system_prompt,
                model_override=settings.agents.llm.default_model,
                memory_namespace="memory_main",
            )
            db.add(main_agent)
            await db.commit()
            logger.info("Created main agent profile")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="SteelClaw",
        description="Self-hosted personal AI assistant",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    from steelclaw.api.agents import router as agents_router
    from steelclaw.api.allowlist import router as allowlist_router
    from steelclaw.api.analytics import router as analytics_router
    from steelclaw.api.config import router as config_router
    from steelclaw.api.health import router as health_router
    from steelclaw.api.history import router as history_router
    from steelclaw.api.persona import router as persona_router
    from steelclaw.api.sessions import router as sessions_router
    from steelclaw.api.tools import router as tools_router
    from steelclaw.api.scheduler import router as scheduler_router
    from steelclaw.api.files import router as files_router
    from steelclaw.api.voice import router as voice_router
    from steelclaw.gateway.router import router as gateway_router
    from steelclaw.scheduler.webhook_server import router as webhook_router

    app.include_router(health_router, tags=["health"])
    app.include_router(config_router, prefix="/api/config", tags=["config"])
    app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(history_router, prefix="/api/history", tags=["history"])
    app.include_router(tools_router, prefix="/api/tools", tags=["tools"])
    # Phase 2: Claude-compatible skills management API
    from steelclaw.api.skills_new import router as skills_new_router
    app.include_router(skills_new_router, prefix="/api/skills", tags=["skills"])
    app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
    app.include_router(allowlist_router, prefix="/api/allowlist", tags=["allowlist"])
    app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(persona_router, prefix="/api/persona", tags=["persona"])
    app.include_router(files_router, prefix="/api/files", tags=["files"])
    app.include_router(voice_router, prefix="/api/voice", tags=["voice"])
    app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
    app.include_router(gateway_router, prefix="/gateway", tags=["gateway"])

    # ── Web Chat UI ─────────────────────────────────────────────────────
    from pathlib import Path as _Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    web_dir = _Path(__file__).parent / "web" / "static"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

        @app.get("/chat")
        async def chat_ui():
            return FileResponse(str(web_dir / "index.html"))

        @app.get("/")
        async def root_redirect():
            from fastapi.responses import RedirectResponse
            return RedirectResponse("/chat")

    return app
