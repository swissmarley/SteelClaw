"""Make.com (Integromat) integration — trigger scenarios via webhook URLs."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("make_integromat")


async def tool_trigger_scenario(payload: str = "{}") -> str:
    """Trigger a Make.com scenario webhook with optional JSON payload."""
    config = _config()
    webhook_url = config.get("webhook_url", "")
    if not webhook_url:
        return "Error: webhook_url not configured. Run: steelclaw skills configure make_integromat"
    try:
        data = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return "Error: Invalid JSON payload"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json=data)
            return f"Scenario triggered. Status: {resp.status_code}. Response: {resp.text[:500]}"
    except Exception as e:
        return f"Error: {e}"
