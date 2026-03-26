"""SQLModel table definitions for SteelClaw persistent storage."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── User ────────────────────────────────────────────────────────────────────


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    display_name: str = ""
    created_at: datetime = Field(default_factory=_now)

    platform_identities: List["PlatformIdentity"] = Relationship(back_populates="user")
    sessions: List["Session"] = Relationship(back_populates="user")


# ── PlatformIdentity ────────────────────────────────────────────────────────


class PlatformIdentity(SQLModel, table=True):
    __tablename__ = "platform_identities"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    platform: str = Field(index=True)
    platform_user_id: str = Field(index=True)
    platform_username: Optional[str] = None
    is_allowed: bool = Field(default=False)

    user: Optional["User"] = Relationship(back_populates="platform_identities")


# ── Session ─────────────────────────────────────────────────────────────────


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    platform: str = Field(index=True)
    platform_chat_id: str = Field(index=True)
    session_type: str = Field(default="dm")  # "dm" | "group"
    unified_session_id: Optional[str] = Field(default=None, index=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    messages: List["Message"] = Relationship(back_populates="session")
    user: Optional["User"] = Relationship(back_populates="sessions")


# ── Message ─────────────────────────────────────────────────────────────────


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    role: str = ""  # "user" | "assistant" | "system"
    content: str = ""
    platform: str = ""
    platform_message_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)

    session: Optional["Session"] = Relationship(back_populates="messages")


# ── AllowlistEntry ──────────────────────────────────────────────────────────


class AllowlistEntry(SQLModel, table=True):
    __tablename__ = "allowlist"

    id: str = Field(default_factory=_uuid, primary_key=True)
    platform: str = Field(index=True)
    platform_user_id: str = ""
    granted_at: datetime = Field(default_factory=_now)
