"""Telegram Bot integration — send messages and get updates."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("telegram_skill")


def _base_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


async def tool_send_message(chat_id: str, text: str, parse_mode: str = "") -> str:
    """Send a message to a Telegram chat."""
    config = _config()
    token = config.get("token", "")
    if not token:
        return "Error: Bot token not configured. Run: steelclaw skills configure telegram_skill"
    try:
        payload: dict = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(token)}/sendMessage",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                msg = data.get("result", {})
                return f"Message sent. Message ID: {msg.get('message_id', 'N/A')}"
            return f"Telegram error: {data.get('description', 'Unknown error')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_updates(limit: int = 10) -> str:
    """Get recent updates sent to the Telegram bot."""
    config = _config()
    token = config.get("token", "")
    if not token:
        return "Error: Bot token not configured. Run: steelclaw skills configure telegram_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(token)}/getUpdates",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return f"Telegram error: {data.get('description', 'Unknown error')}"
            updates = data.get("result", [])
            if not updates:
                return "No recent updates."
            lines = []
            for u in updates:
                msg = u.get("message", {})
                sender = msg.get("from", {}).get("first_name", "unknown")
                text = msg.get("text", "")[:200]
                lines.append(f"- [{sender}]: {text}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
