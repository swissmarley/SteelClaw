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
    status: str = Field(default="active", index=True)  # "active" | "idle" | "closed"
    connector_type: Optional[str] = Field(default=None)  # "telegram" | "discord" | "websocket" | etc.
    last_activity_at: datetime = Field(default_factory=_now)
    agent_id: Optional[str] = Field(default=None, foreign_key="agents.id")
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    messages: List["Message"] = Relationship(back_populates="session")
    user: Optional["User"] = Relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.status != "closed"

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.status = "active" if value else "closed"


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
    model: Optional[str] = None
    token_usage_prompt: Optional[int] = None
    token_usage_completion: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: datetime = Field(default_factory=_now)

    session: Optional["Session"] = Relationship(back_populates="messages")


# ── AllowlistEntry ──────────────────────────────────────────────────────────


class AllowlistEntry(SQLModel, table=True):
    __tablename__ = "allowlist"

    id: str = Field(default_factory=_uuid, primary_key=True)
    platform: str = Field(index=True)
    platform_user_id: str = ""
    granted_at: datetime = Field(default_factory=_now)


# ── AgentProfile ────────────────────────────────────────────────────────────


class AgentProfile(SQLModel, table=True):
    __tablename__ = "agents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, unique=True)
    display_name: str = ""
    is_main: bool = Field(default=False)
    system_prompt: str = ""
    persona_json: Optional[str] = None  # JSON: {agent_name, user_name, tone, style, goals[]}
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    memory_namespace: str = Field(default_factory=lambda: f"memory_{_uuid()[:8]}")
    is_active: bool = Field(default=True)
    parent_agent_id: Optional[str] = Field(default=None, foreign_key="agents.id", index=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ── UserFact ────────────────────────────────────────────────────────────────


class UserFact(SQLModel, table=True):
    __tablename__ = "user_facts"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    fact_key: str = ""  # e.g. "name", "timezone", "preference_language"
    fact_value: str = ""
    source: str = "conversation"  # "conversation" | "manual" | "setup"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


# ── MemoryEntry ─────────────────────────────────────────────────────────────


class MemoryEntry(SQLModel, table=True):
    __tablename__ = "memory_entries"

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: Optional[str] = Field(default=None, foreign_key="sessions.id")
    agent_id: Optional[str] = Field(default=None, foreign_key="agents.id")
    content_hash: str = Field(default="", index=True)
    content_preview: str = ""  # first 200 chars
    source_type: str = "message"  # "message" | "summary" | "fact"
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


# ── ReflectionLog ────────────────────────────────────────────────────────────


class ReflectionLog(SQLModel, table=True):
    """Audit log for agent self-reflections and autonomous skill creation attempts.

    Created after the agent completes a task that triggered the reflection
    threshold (default: 5+ tool calls in a single session).
    """

    __tablename__ = "reflection_logs"

    id: str = Field(default_factory=_uuid, primary_key=True)
    agent_id: str = Field(default="", index=True)
    session_id: str = Field(default="", index=True)
    tool_call_count: int = Field(default=0)
    reflection_summary: str = ""  # what the agent reflected on
    skill_created: Optional[str] = None  # skill name if a new skill was generated
    skill_path: Optional[str] = None  # path to generated skill directory
    created_at: datetime = Field(default_factory=_now)
