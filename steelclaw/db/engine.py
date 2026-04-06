"""Async SQLAlchemy engine and session factory for SQLite."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

logger = logging.getLogger("steelclaw.db")

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str, echo: bool = False) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=echo)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_engine():
    """Return the raw async engine (used by Alembic and migration runner)."""
    return _engine


async def create_tables() -> None:
    if _engine is None:
        raise RuntimeError("Engine not initialised — call init_engine() first")
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    # After creating tables, ensure existing tables have all new columns
    await _apply_schema_updates()


async def _apply_schema_updates() -> None:
    """Add missing columns to existing tables (SQLite ALTER TABLE ADD COLUMN).

    This handles the case where the SQLite database was created before new columns
    were added to the models. ``create_all`` only creates tables that don't exist —
    it won't add columns to existing tables.
    """
    # Map of table -> [(column_name, column_sql_type, default_expr)]
    _expected_columns: dict[str, list[tuple[str, str, str | None]]] = {
        "sessions": [
            ("status", "VARCHAR", "'active'"),
            ("connector_type", "VARCHAR", None),
            ("last_activity_at", "DATETIME", None),
            ("agent_id", "VARCHAR", None),
        ],
        "messages": [
            ("model", "VARCHAR", None),
            ("token_usage_prompt", "INTEGER", None),
            ("token_usage_completion", "INTEGER", None),
            ("cost_usd", "FLOAT", None),
        ],
        "agents": [
            ("parent_agent_id", "VARCHAR", None),
        ],
    }

    async with _engine.begin() as conn:
        for table, columns in _expected_columns.items():
            # Check which columns already exist
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result.fetchall()}

            for col_name, col_type, default in columns:
                if col_name not in existing:
                    default_clause = f" DEFAULT {default}" if default else ""
                    sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}{default_clause}"
                    await conn.execute(text(sql))
                    logger.info("Added column %s.%s", table, col_name)

        # Handle the old is_active column (NOT NULL in pre-migration DBs)
        # Since we can't drop columns in SQLite, we need to recreate the table
        # without is_active, or work around it. The simplest fix: set a default
        # on the old column so INSERTs that don't include it won't fail.
        result = await conn.execute(text("PRAGMA table_info(sessions)"))
        session_cols = {}
        for row in result.fetchall():
            session_cols[row[1]] = {"notnull": row[3], "default": row[4]}

        if "is_active" in session_cols:
            # Populate status from is_active before we rebuild
            await conn.execute(text(
                "UPDATE sessions SET status = 'closed' WHERE is_active = 0"
            ))
            # SQLite can't ALTER COLUMN, so rebuild the table without is_active
            # to prevent NOT NULL violations on INSERT
            await _rebuild_sessions_without_is_active(conn)
        # Populate connector_type from platform
        await conn.execute(text(
            "UPDATE sessions SET connector_type = platform WHERE connector_type IS NULL"
        ))
        # Populate last_activity_at from updated_at
        await conn.execute(text(
            "UPDATE sessions SET last_activity_at = updated_at WHERE last_activity_at IS NULL"
        ))

        # Create new tables if they don't exist (agents, user_facts, memory_entries)
        # This is already handled by create_all above, but the column additions
        # above only work for existing tables.

    logger.info("Schema update check complete")


async def _rebuild_sessions_without_is_active(conn) -> None:
    """Rebuild the sessions table without the legacy is_active column.

    SQLite doesn't support DROP COLUMN (before 3.35) or ALTER COLUMN,
    so we recreate the table preserving all data.
    """
    await conn.execute(text("""
        CREATE TABLE sessions_new (
            id VARCHAR PRIMARY KEY,
            platform VARCHAR NOT NULL,
            platform_chat_id VARCHAR NOT NULL,
            session_type VARCHAR NOT NULL DEFAULT 'dm',
            unified_session_id VARCHAR,
            user_id VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'active',
            connector_type VARCHAR,
            last_activity_at DATETIME,
            agent_id VARCHAR,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """))
    await conn.execute(text("""
        INSERT INTO sessions_new
            (id, platform, platform_chat_id, session_type, unified_session_id,
             user_id, status, connector_type, last_activity_at, agent_id,
             created_at, updated_at)
        SELECT id, platform, platform_chat_id, session_type, unified_session_id,
               user_id, status, connector_type, last_activity_at, agent_id,
               created_at, updated_at
        FROM sessions
    """))
    await conn.execute(text("DROP TABLE sessions"))
    await conn.execute(text("ALTER TABLE sessions_new RENAME TO sessions"))
    # Recreate indexes
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_platform ON sessions (platform)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_platform_chat_id ON sessions (platform_chat_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_unified_session_id ON sessions (unified_session_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions (status)"))
    logger.info("Rebuilt sessions table — removed legacy is_active column")


async def run_migrations() -> None:
    """Run Alembic migrations programmatically."""
    from alembic.config import Config

    alembic_cfg = Config()
    migrations_dir = str(Path(__file__).parent / "migrations")
    alembic_cfg.set_main_option("script_location", migrations_dir)

    if _engine is None:
        raise RuntimeError("Engine not initialised — call init_engine() first")

    alembic_cfg.set_main_option("sqlalchemy.url", str(_engine.url))

    # Run upgrade in a way compatible with async
    from alembic import command as alembic_command
    import asyncio

    def _run_upgrade():
        alembic_command.upgrade(alembic_cfg, "head")

    # Alembic manages its own async internally via env.py
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_upgrade)
    logger.info("Database migrations applied")


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()


async def get_async_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Session factory not initialised — call init_engine() first")
    async with _session_factory() as session:
        yield session
