"""Normalised message schemas shared across all connectors."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """A message arriving from any platform, normalised to a common shape."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: str
    platform_chat_id: str
    platform_user_id: str
    platform_message_id: str | None = None
    platform_username: str | None = None
    content: str
    attachments: list[dict] | None = None
    is_group: bool = False
    is_mention: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict | None = None


class OutboundMessage(BaseModel):
    """A message from the system back to a platform."""

    platform: str
    platform_chat_id: str
    content: str
    reply_to_message_id: str | None = None
    metadata: dict | None = None
