"""FastAPI application factory with async lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from steelclaw.db.engine import create_tables, dispose_engine, init_engine
from steelclaw.gateway.registry import ConnectorRegistry
from steelclaw.settings import Settings

logger = logging.getLogger("steelclaw")


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

    # ── Skill system ────────────────────────────────────────────────────
    from steelclaw.skills.registry import SkillRegistry

    # Resolve relative skill paths against project root
    skill_settings = settings.agents.skills
    skill_settings.bundled_dir = str(resolve_path(skill_settings.bundled_dir))
    skill_settings.global_dir = str(resolve_path(skill_settings.global_dir))
    skill_settings.workspace_dir = str(resolve_path(skill_settings.workspace_dir))

    skill_registry = SkillRegistry(skill_settings)
    skill_registry.load_all()

    # Verify critical skills loaded
    for critical in ("web_search",):
        if skill_registry.get_skill(critical) is None:
            logger.warning("Critical skill '%s' failed to load — agent may lack web access", critical)
        else:
            logger.info("Critical skill '%s' loaded OK", critical)

    app.state.skill_registry = skill_registry

    # ── Security ────────────────────────────────────────────────────────
    from steelclaw.security.permissions import PermissionManager
    from steelclaw.security.sandbox import set_permission_manager

    # Resolve approvals file path
    settings.agents.security.approvals_file = str(
        resolve_path(settings.agents.security.approvals_file)
    )
    permission_manager = PermissionManager(settings.agents.security)
    set_permission_manager(permission_manager)
    app.state.permission_manager = permission_manager

    # ── Memory system (ChromaDB) ────────────────────────────────────────
    from steelclaw.memory.ingestion import MemoryIngestor
    from steelclaw.memory.retrieval import MemoryRetriever
    from steelclaw.memory.vector_store import VectorStore

    vector_store = VectorStore(settings.agents.memory)
    memory_retriever = MemoryRetriever(vector_store)
    memory_ingestor = MemoryIngestor(vector_store)
    app.state.vector_store = vector_store
    app.state.memory_retriever = memory_retriever
    app.state.memory_ingestor = memory_ingestor

    # ── Agent router (LLM-powered) ─────────────────────────────────────
    from steelclaw.agents.router import AgentRouter
    from steelclaw.gateway.router import set_agent_router, set_memory_ingestor

    agent_router = AgentRouter(
        settings=settings.agents,
        skill_registry=skill_registry,
    )
    agent_router.set_memory(memory_retriever, memory_ingestor)
    set_agent_router(agent_router)
    set_memory_ingestor(memory_ingestor)
    app.state.agent_router = agent_router

    # ── Ensure main agent exists ────────────────────────────────────────
    await _ensure_main_agent(settings)

    # ── Task scheduler ──────────────────────────────────────────────────
    from steelclaw.scheduler.engine import TaskEngine

    task_engine = TaskEngine(settings.agents.scheduler)
    task_engine.start()
    app.state.task_engine = task_engine

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
    from steelclaw.gateway.router import process_message

    registry = ConnectorRegistry(settings.gateway)

    async def _connector_handler(inbound):
        """Handle messages from platform connectors (Telegram, Discord, etc.)."""
        from steelclaw.db.engine import get_async_session

        outbound = None
        try:
            async for db in get_async_session():
                outbound = await process_message(inbound, settings.gateway, db)
        except Exception:
            logger.exception("Error processing connector message (%s)", inbound.platform)
        if outbound:
            connector = registry.get(inbound.platform)
            if connector:
                await connector.send(outbound)

    registry.set_handler(_connector_handler)
    await registry.start_all()
    app.state.registry = registry

    logger.info("SteelClaw started on %s:%s", settings.server.host, settings.server.port)
    yield

    # ── Shutdown ────────────────────────────────────────────────────────
    task_engine.stop()
    await registry.stop_all()
    await dispose_engine()
    logger.info("SteelClaw shut down")


async def _ensure_main_agent(settings: Settings) -> None:
    """Create the main agent profile if it doesn't exist yet."""
    from sqlalchemy import select

    from steelclaw.db.engine import get_async_session
    from steelclaw.db.models import AgentProfile

    async for db in get_async_session():
        stmt = select(AgentProfile).where(AgentProfile.is_main.is_(True))
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
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
    from steelclaw.api.analytics import router as analytics_router
    from steelclaw.api.config import router as config_router
    from steelclaw.api.health import router as health_router
    from steelclaw.api.history import router as history_router
    from steelclaw.api.persona import router as persona_router
    from steelclaw.api.sessions import router as sessions_router
    from steelclaw.api.skills import router as skills_router
    from steelclaw.api.scheduler import router as scheduler_router
    from steelclaw.api.files import router as files_router
    from steelclaw.api.voice import router as voice_router
    from steelclaw.gateway.router import router as gateway_router
    from steelclaw.scheduler.webhook_server import router as webhook_router

    app.include_router(health_router, tags=["health"])
    app.include_router(config_router, prefix="/api/config", tags=["config"])
    app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(history_router, prefix="/api/history", tags=["history"])
    app.include_router(skills_router, prefix="/api/skills", tags=["skills"])
    app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
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
