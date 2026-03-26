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
    settings: Settings = app.state.settings

    # Ensure data directory exists for SQLite
    db_url = settings.database.url
    if ":///" in db_url:
        db_path = db_url.split(":///", 1)[1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Database ────────────────────────────────────────────────────────
    init_engine(settings.database.url, echo=settings.database.echo)
    await create_tables()
    logger.info("Database initialised")

    # ── Skill system ────────────────────────────────────────────────────
    from steelclaw.skills.registry import SkillRegistry

    skill_registry = SkillRegistry(settings.agents.skills)
    skill_registry.load_all()
    app.state.skill_registry = skill_registry

    # ── Security ────────────────────────────────────────────────────────
    from steelclaw.security.permissions import PermissionManager
    from steelclaw.security.sandbox import set_permission_manager

    permission_manager = PermissionManager(settings.agents.security)
    set_permission_manager(permission_manager)
    app.state.permission_manager = permission_manager

    # ── Agent router (LLM-powered) ─────────────────────────────────────
    from steelclaw.agents.router import AgentRouter
    from steelclaw.gateway.router import set_agent_router

    agent_router = AgentRouter(
        settings=settings.agents,
        skill_registry=skill_registry,
    )
    set_agent_router(agent_router)
    app.state.agent_router = agent_router

    # ── Task scheduler ──────────────────────────────────────────────────
    from steelclaw.scheduler.engine import TaskEngine

    task_engine = TaskEngine(settings.agents.scheduler)
    task_engine.start()
    app.state.task_engine = task_engine

    # ── Messaging gateway ───────────────────────────────────────────────
    from steelclaw.gateway.router import process_message

    registry = ConnectorRegistry(settings.gateway)

    async def _connector_handler(inbound):
        """Handle messages from platform connectors (Telegram, Discord, etc.)."""
        from steelclaw.db.engine import get_async_session

        async for db in get_async_session():
            outbound = await process_message(inbound, settings.gateway, db)
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


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="SteelClaw",
        description="Self-hosted personal AI assistant",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    from steelclaw.api.config import router as config_router
    from steelclaw.api.health import router as health_router
    from steelclaw.api.history import router as history_router
    from steelclaw.api.sessions import router as sessions_router
    from steelclaw.api.skills import router as skills_router
    from steelclaw.api.scheduler import router as scheduler_router
    from steelclaw.gateway.router import router as gateway_router

    app.include_router(health_router, tags=["health"])
    app.include_router(config_router, prefix="/api/config", tags=["config"])
    app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(history_router, prefix="/api/history", tags=["history"])
    app.include_router(skills_router, prefix="/api/skills", tags=["skills"])
    app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
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
