"""Slack integration — send messages, list channels, get history."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "bot_token", "label": "Slack Bot Token", "type": "password", "test_url": "https://slack.com/api/auth.test"},
]

BASE_URL = "https://slack.com/api"


def _config() -> dict:
    return get_all_credentials("slack_skill")


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def tool_send_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure slack_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/chat.postMessage",
                headers=_headers(api_key),
                json={"channel": channel, "text": text},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return f"Message sent to {channel}. Timestamp: {data.get('ts', 'N/A')}"
            return f"Slack error: {data.get('error', 'Unknown error')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_channels(limit: int = 20) -> str:
    """List channels in the Slack workspace."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure slack_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/conversations.list",
                headers=_headers(api_key),
                params={"limit": limit, "types": "public_channel,private_channel"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return f"Slack error: {data.get('error', 'Unknown error')}"
            channels = data.get("channels", [])
            if not channels:
                return "No channels found."
            lines = []
            for ch in channels:
                members = ch.get("num_members", 0)
                lines.append(f"- #{ch['name']} (ID: {ch['id']}, {members} members)")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_channel_history(channel: str, limit: int = 10) -> str:
    """Get recent messages from a Slack channel."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure slack_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/conversations.history",
                headers=_headers(api_key),
                params={"channel": channel, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return f"Slack error: {data.get('error', 'Unknown error')}"
            messages = data.get("messages", [])
            if not messages:
                return "No messages found."
            lines = []
            for msg in messages:
                user = msg.get("user", "unknown")
                text = msg.get("text", "")[:200]
                lines.append(f"- [{user}]: {text}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
