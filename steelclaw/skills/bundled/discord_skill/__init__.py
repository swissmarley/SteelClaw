"""Discord integration — send messages, list channels, get messages."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://discord.com/api/v10"


def _config() -> dict:
    return get_all_credentials("discord_skill")


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bot {api_key}", "Content-Type": "application/json"}


async def tool_send_message(channel_id: str, content: str) -> str:
    """Send a message to a Discord channel."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure discord_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/channels/{channel_id}/messages",
                headers=_headers(api_key),
                json={"content": content},
            )
            resp.raise_for_status()
            msg = resp.json()
            return f"Message sent. ID: {msg['id']}"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_channels(guild_id: str) -> str:
    """List channels in a Discord guild."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure discord_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/guilds/{guild_id}/channels",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            channels = resp.json()
            if not channels:
                return "No channels found."
            lines = []
            type_map = {0: "text", 2: "voice", 4: "category", 5: "announcement", 13: "stage", 15: "forum"}
            for ch in channels:
                ch_type = type_map.get(ch.get("type", 0), "other")
                lines.append(f"- #{ch.get('name', 'N/A')} (ID: {ch['id']}, {ch_type})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_messages(channel_id: str, limit: int = 10) -> str:
    """Get recent messages from a Discord channel."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure discord_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/channels/{channel_id}/messages",
                headers=_headers(api_key),
                params={"limit": limit},
            )
            resp.raise_for_status()
            messages = resp.json()
            if not messages:
                return "No messages found."
            lines = []
            for msg in messages:
                author = msg.get("author", {}).get("username", "unknown")
                content = msg.get("content", "")[:200]
                lines.append(f"- [{author}]: {content}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
