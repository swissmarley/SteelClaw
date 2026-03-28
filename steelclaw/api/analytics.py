"""REST API for usage analytics and cost tracking."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Message as DBMessage, Session as DBSession

router = APIRouter()


def _parse_date(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return default


@router.get("/summary")
async def analytics_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Summary cards: total tokens, cost, sessions, messages."""
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    msg_stmt = select(
        func.count(DBMessage.id),
        func.coalesce(func.sum(DBMessage.token_usage_prompt), 0),
        func.coalesce(func.sum(DBMessage.token_usage_completion), 0),
        func.coalesce(func.sum(DBMessage.cost_usd), 0.0),
    ).where(
        DBMessage.created_at >= start,
        DBMessage.created_at <= end,
    )
    result = await db.execute(msg_stmt)
    row = result.one()

    session_stmt = select(func.count(DBSession.id)).where(
        DBSession.created_at >= start,
        DBSession.created_at <= end,
    )
    session_result = await db.execute(session_stmt)
    total_sessions = session_result.scalar() or 0

    active_stmt = select(func.count(DBSession.id)).where(
        DBSession.status == "active",
    )
    active_result = await db.execute(active_stmt)
    active_sessions = active_result.scalar() or 0

    return {
        "total_messages": row[0],
        "total_prompt_tokens": row[1],
        "total_completion_tokens": row[2],
        "total_tokens": row[1] + row[2],
        "total_cost_usd": round(float(row[3]), 4),
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
    }


@router.get("/usage-over-time")
async def usage_over_time(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    granularity: str = Query("day", pattern="^(day|hour)$"),
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """Time-series token usage and cost data."""
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    # SQLite strftime for grouping
    if granularity == "hour":
        date_fmt = "%Y-%m-%d %H:00"
    else:
        date_fmt = "%Y-%m-%d"

    date_expr = func.strftime(date_fmt, DBMessage.created_at)

    stmt = (
        select(
            date_expr.label("date"),
            func.coalesce(func.sum(DBMessage.token_usage_prompt), 0).label("prompt_tokens"),
            func.coalesce(func.sum(DBMessage.token_usage_completion), 0).label("completion_tokens"),
            func.coalesce(func.sum(DBMessage.cost_usd), 0.0).label("cost"),
            func.count(DBMessage.id).label("messages"),
        )
        .where(
            DBMessage.created_at >= start,
            DBMessage.created_at <= end,
            DBMessage.role == "assistant",
        )
        .group_by(date_expr)
        .order_by(date_expr)
    )

    result = await db.execute(stmt)
    return [
        {
            "date": row.date,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost": round(float(row.cost), 6),
            "messages": row.messages,
        }
        for row in result.all()
    ]


@router.get("/by-model")
async def usage_by_model(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    stmt = (
        select(
            DBMessage.model,
            func.coalesce(func.sum(DBMessage.token_usage_prompt), 0).label("prompt_tokens"),
            func.coalesce(func.sum(DBMessage.token_usage_completion), 0).label("completion_tokens"),
            func.coalesce(func.sum(DBMessage.cost_usd), 0.0).label("cost"),
            func.count(DBMessage.id).label("message_count"),
        )
        .where(
            DBMessage.created_at >= start,
            DBMessage.created_at <= end,
            DBMessage.model.isnot(None),
        )
        .group_by(DBMessage.model)
        .order_by(func.sum(DBMessage.cost_usd).desc())
    )

    result = await db.execute(stmt)
    return [
        {
            "model": row.model or "unknown",
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.prompt_tokens + row.completion_tokens,
            "cost": round(float(row.cost), 6),
            "message_count": row.message_count,
        }
        for row in result.all()
    ]


@router.get("/by-agent")
async def usage_by_agent(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    stmt = (
        select(
            DBMessage.agent_id,
            func.coalesce(func.sum(DBMessage.token_usage_prompt), 0).label("prompt_tokens"),
            func.coalesce(func.sum(DBMessage.token_usage_completion), 0).label("completion_tokens"),
            func.coalesce(func.sum(DBMessage.cost_usd), 0.0).label("cost"),
            func.count(DBMessage.id).label("message_count"),
        )
        .where(
            DBMessage.created_at >= start,
            DBMessage.created_at <= end,
        )
        .group_by(DBMessage.agent_id)
    )

    result = await db.execute(stmt)
    return [
        {
            "agent_id": row.agent_id or "main",
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.prompt_tokens + row.completion_tokens,
            "cost": round(float(row.cost), 6),
            "message_count": row.message_count,
        }
        for row in result.all()
    ]


@router.get("/session-histogram")
async def session_histogram(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """Distribution of messages per session."""
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    # First get message counts per session
    subq = (
        select(
            DBMessage.session_id,
            func.count(DBMessage.id).label("msg_count"),
        )
        .where(
            DBMessage.created_at >= start,
            DBMessage.created_at <= end,
        )
        .group_by(DBMessage.session_id)
        .subquery()
    )

    # Bucket into ranges
    buckets = [
        ("1-5", 1, 5),
        ("6-10", 6, 10),
        ("11-25", 11, 25),
        ("26-50", 26, 50),
        ("51-100", 51, 100),
        ("100+", 101, 999999),
    ]

    result_data = []
    for label, low, high in buckets:
        stmt = select(func.count()).select_from(subq).where(
            subq.c.msg_count >= low,
            subq.c.msg_count <= high,
        )
        count_result = await db.execute(stmt)
        count = count_result.scalar() or 0
        result_data.append({"bucket": label, "count": count})

    return result_data


@router.get("/export")
async def export_csv(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """Export message data as CSV."""
    now = datetime.now(timezone.utc)
    start = _parse_date(from_date, now - timedelta(days=30))
    end = _parse_date(to_date, now)

    stmt = (
        select(DBMessage)
        .where(
            DBMessage.created_at >= start,
            DBMessage.created_at <= end,
        )
        .order_by(DBMessage.created_at)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "session_id", "role", "platform", "model",
        "prompt_tokens", "completion_tokens", "cost_usd",
        "content_preview", "created_at",
    ])
    for msg in messages:
        writer.writerow([
            msg.id,
            msg.session_id,
            msg.role,
            msg.platform,
            msg.model or "",
            msg.token_usage_prompt or 0,
            msg.token_usage_completion or 0,
            msg.cost_usd or 0.0,
            msg.content[:100].replace("\n", " "),
            msg.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=steelclaw_usage.csv"},
    )
