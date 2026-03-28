"""Session heartbeat — background task for idle/close detection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Session as DBSession
from steelclaw.settings import SessionLifecycleSettings

logger = logging.getLogger("steelclaw.heartbeat")


async def run_heartbeat(lifecycle_settings: SessionLifecycleSettings) -> None:
    """Check for idle and stale sessions and transition their status."""
    now = datetime.now(timezone.utc)

    idle_threshold = now - timedelta(minutes=lifecycle_settings.idle_timeout_minutes)
    close_threshold = now - timedelta(minutes=lifecycle_settings.close_timeout_minutes)

    async for db in get_async_session():
        # Transition active → idle
        idle_stmt = (
            update(DBSession)
            .where(
                DBSession.status == "active",
                DBSession.last_activity_at < idle_threshold,
            )
            .values(status="idle", updated_at=now)
        )
        result = await db.execute(idle_stmt)
        idle_count = result.rowcount

        # Transition idle → closed
        close_stmt = (
            update(DBSession)
            .where(
                DBSession.status == "idle",
                DBSession.last_activity_at < close_threshold,
            )
            .values(status="closed", updated_at=now)
        )
        result = await db.execute(close_stmt)
        close_count = result.rowcount

        await db.commit()

        if idle_count or close_count:
            logger.info(
                "Heartbeat: %d sessions → idle, %d sessions → closed",
                idle_count,
                close_count,
            )
