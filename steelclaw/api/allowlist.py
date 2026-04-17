"""REST API for DM allowlist management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import AllowlistEntry

router = APIRouter()


class AllowlistEntryCreate(BaseModel):
    platform: str
    platform_user_id: str


class AllowlistEntryResponse(BaseModel):
    id: str
    platform: str
    platform_user_id: str
    granted_at: str


@router.get("")
async def list_allowlist() -> list[AllowlistEntryResponse]:
    """List all allowlist entries."""
    async for db in get_async_session():
        result = await db.execute(select(AllowlistEntry).order_by(AllowlistEntry.granted_at))
        entries = result.scalars().all()
        return [
            AllowlistEntryResponse(
                id=e.id,
                platform=e.platform,
                platform_user_id=e.platform_user_id,
                granted_at=e.granted_at.isoformat(),
            )
            for e in entries
        ]
    return []


@router.post("")
async def add_allowlist_entry(body: AllowlistEntryCreate) -> dict:
    """Add a user to the DM allowlist."""
    async for db in get_async_session():
        # Check if already exists
        existing = await db.execute(
            select(AllowlistEntry).where(
                AllowlistEntry.platform == body.platform,
                AllowlistEntry.platform_user_id == body.platform_user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, "User already on allowlist")

        entry = AllowlistEntry(
            platform=body.platform,
            platform_user_id=body.platform_user_id,
        )
        db.add(entry)
        await db.commit()
        return {"status": "added", "id": entry.id}


@router.delete("/{platform}/{platform_user_id:path}")
async def remove_allowlist_entry(platform: str, platform_user_id: str) -> dict:
    """Remove a user from the DM allowlist."""
    async for db in get_async_session():
        result = await db.execute(
            select(AllowlistEntry).where(
                AllowlistEntry.platform == platform,
                AllowlistEntry.platform_user_id == platform_user_id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(404, "Entry not found")
        await db.delete(entry)
        await db.commit()
        return {"status": "removed"}