"""Webhook trigger endpoint — receives POST requests and fires scheduled actions."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("steelclaw.scheduler.webhook")

router = APIRouter()

# Registry: webhook_id -> {trigger_id, secret, callback_prompt, last_fired, fire_count}
_webhook_registry: dict[str, dict[str, Any]] = {}


def register_webhook(trigger_id: str, secret: str = "", callback_prompt: str = "") -> str:
    """Register a webhook trigger and return its unique webhook ID."""
    webhook_id = uuid.uuid4().hex[:12]
    _webhook_registry[webhook_id] = {
        "trigger_id": trigger_id,
        "secret": secret,
        "callback_prompt": callback_prompt,
        "last_fired": None,
        "fire_count": 0,
    }
    logger.info("Registered webhook %s for trigger %s", webhook_id, trigger_id)
    return webhook_id


def unregister_webhook(webhook_id: str) -> None:
    """Remove a webhook registration."""
    _webhook_registry.pop(webhook_id, None)


def list_webhooks() -> list[dict[str, Any]]:
    """List all registered webhooks."""
    return [
        {"webhook_id": wid, **{k: v for k, v in data.items() if k != "secret"}}
        for wid, data in _webhook_registry.items()
    ]


@router.post("/trigger/{webhook_id}")
async def receive_webhook(webhook_id: str, request: Request) -> dict:
    """Receive an incoming webhook POST and fire the associated trigger."""
    entry = _webhook_registry.get(webhook_id)
    if not entry:
        raise HTTPException(404, "Webhook not found")

    # Optional HMAC-SHA256 verification
    if entry.get("secret"):
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()
        expected = "sha256=" + hmac.new(
            entry["secret"].encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            raise HTTPException(401, "Invalid signature")

    # Parse body
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body_data = await request.json()
    else:
        body_data = {"raw": (await request.body()).decode(errors="replace")}

    # Update stats
    entry["last_fired"] = datetime.now(timezone.utc).isoformat()
    entry["fire_count"] = entry.get("fire_count", 0) + 1

    logger.info(
        "Webhook %s fired (trigger: %s, count: %d)",
        webhook_id, entry["trigger_id"], entry["fire_count"],
    )

    return {
        "status": "triggered",
        "webhook_id": webhook_id,
        "trigger_id": entry["trigger_id"],
        "fire_count": entry["fire_count"],
    }
