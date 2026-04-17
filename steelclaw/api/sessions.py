"""REST API for session management."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Message as DBMessage, Session as DBSession

router = APIRouter()


class StatusUpdate(BaseModel):
    status: str  # "active" | "idle" | "closed"


@router.get("")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    platform: str | None = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    stmt = select(DBSession).order_by(DBSession.updated_at.desc()).offset(offset).limit(limit)
    if status:
        stmt = stmt.where(DBSession.status == status)
    else:
        # Default: show non-closed sessions
        stmt = stmt.where(DBSession.status != "closed")
    if platform:
        stmt = stmt.where(DBSession.platform == platform)
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


@router.patch("/{session_id}/status")
async def update_session_status(
    session_id: str,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    if body.status not in ("active", "idle", "closed"):
        raise HTTPException(400, "Status must be 'active', 'idle', or 'closed'")
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.status = body.status
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "updated", "session_id": session_id, "new_status": body.status}


@router.post("/{session_id}/reset")
async def reset_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Reset a session: clear all messages but keep the session alive."""
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Delete all messages in this session
    await db.execute(delete(DBMessage).where(DBMessage.session_id == session_id))

    # Reset session state
    now = datetime.now(timezone.utc)
    session.status = "active"
    session.last_activity_at = now
    session.updated_at = now
    await db.commit()

    return {"status": "reset", "session_id": session_id}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Delete a session and all its messages permanently."""
    session = await db.get(DBSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Delete messages first (FK constraint)
    await db.execute(delete(DBMessage).where(DBMessage.session_id == session_id))
    await db.delete(session)
    await db.commit()

    return {"status": "deleted", "session_id": session_id}


def _serialise(session: DBSession) -> dict:
    return {
        "id": session.id,
        "platform": session.platform,
        "platform_chat_id": session.platform_chat_id,
        "session_type": session.session_type,
        "unified_session_id": session.unified_session_id,
        "user_id": session.user_id,
        "status": session.status,
        "connector_type": session.connector_type,
        "last_activity_at": session.last_activity_at.isoformat() if session.last_activity_at else None,
        "agent_id": session.agent_id,
        "is_active": session.is_active,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }
