"""Data models for interactive permission requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class PermissionDecision(str, Enum):
    """User's decision on a permission request."""
    APPROVE_ONCE = "approve_once"
    APPROVE_SESSION = "approve_session"
    DENY = "deny"


class PermissionRequestStatus(str, Enum):
    """Status of a permission request."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class PermissionRequest:
    """A permission request that needs user approval.

    Created when a command needs approval and broadcast to all connected channels.
    """
    request_id: str
    command: str
    tool_name: str
    session_id: str
    platform: str
    platform_chat_id: str
    timeout_seconds: int
    created_at: datetime
    skill_name: Optional[str] = None
    status: PermissionRequestStatus = PermissionRequestStatus.PENDING
    context: Optional[str] = None

    @classmethod
    def create(
        cls,
        command: str,
        tool_name: str,
        session_id: str,
        platform: str,
        platform_chat_id: str,
        timeout_seconds: int = 300,
        skill_name: Optional[str] = None,
        context: Optional[str] = None,
    ) -> "PermissionRequest":
        """Factory method to create a new permission request."""
        return cls(
            request_id=str(uuid.uuid4()),
            command=command,
            tool_name=tool_name,
            session_id=session_id,
            platform=platform,
            platform_chat_id=platform_chat_id,
            timeout_seconds=timeout_seconds,
            created_at=datetime.now(timezone.utc),
            skill_name=skill_name,
            context=context,
        )

    def to_dict(self) -> dict:
        """Serialize for WebSocket transmission."""
        return {
            "request_id": self.request_id,
            "command": self.command,
            "tool_name": self.tool_name,
            "skill_name": self.skill_name,
            "session_id": self.session_id,
            "timeout_seconds": self.timeout_seconds,
            "context": self.context,
            "options": ["approve_once", "approve_session", "deny"],
        }


@dataclass
class PermissionResponse:
    """A user's response to a permission request."""
    request_id: str
    decision: PermissionDecision
    user_id: str
    platform: str
    responded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize for WebSocket transmission."""
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "user_id": self.user_id,
            "platform": self.platform,
        }


@dataclass
class ResolvedRequest:
    """Broadcast when a permission request is resolved."""
    request_id: str
    decision: PermissionDecision
    resolved_by: str  # Format: "platform:user_id"
    original_command: str

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "resolved_by": self.resolved_by,
            "original_command": self.original_command,
        }