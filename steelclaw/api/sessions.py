"""REST API for session management."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Session as DBSession

router = APIRouter()


@router.get("")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    stmt = (
        select(DBSession)
        .where(DBSession.is_active.is_(True))
        .order_by(DBSession.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [_serialise(s) for s in sessions]


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return _serialise(session)


@router.get("/unified/{unified_session_id}")
async def get_unified_sessions(
    unified_session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    stmt = select(DBSession).where(DBSession.unified_session_id == unified_session_id)
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [_serialise(s) for s in sessions]


@router.delete("/{session_id}")
async def deactivate_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.is_active = False
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "deactivated", "session_id": session_id}


def _serialise(session: DBSession) -> dict:
    return {
        "id": session.id,
        "platform": session.platform,
        "platform_chat_id": session.platform_chat_id,
        "session_type": session.session_type,
        "unified_session_id": session.unified_session_id,
        "user_id": session.user_id,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }
