"""REST API for message history."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Message as DBMessage, Session as DBSession

router = APIRouter()


@router.get("/{session_id}")
async def get_history(
    session_id: str,
    limit: int = 50,
    before: datetime | None = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    stmt = (
        select(DBMessage)
        .where(DBMessage.session_id == session_id)
        .order_by(DBMessage.created_at.desc())
        .limit(limit)
    )
    if before:
        stmt = stmt.where(DBMessage.created_at < before)

    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [_serialise(m) for m in reversed(messages)]


@router.get("/unified/{unified_session_id}")
async def get_unified_history(
    unified_session_id: str,
    limit: int = 50,
    before: datetime | None = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    # Find all session IDs sharing this unified ID
    session_stmt = select(DBSession.id).where(
        DBSession.unified_session_id == unified_session_id
    )
    session_result = await db.execute(session_stmt)
    session_ids = [row[0] for row in session_result.all()]

    if not session_ids:
        raise HTTPException(404, "No sessions found for unified ID")

    stmt = (
        select(DBMessage)
        .where(DBMessage.session_id.in_(session_ids))
        .order_by(DBMessage.created_at.desc())
        .limit(limit)
    )
    if before:
        stmt = stmt.where(DBMessage.created_at < before)

    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [_serialise(m) for m in reversed(messages)]


def _serialise(msg: DBMessage) -> dict:
    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "role": msg.role,
        "content": msg.content,
        "platform": msg.platform,
        "platform_message_id": msg.platform_message_id,
        "agent_id": msg.agent_id,
        "created_at": msg.created_at.isoformat(),
    }
