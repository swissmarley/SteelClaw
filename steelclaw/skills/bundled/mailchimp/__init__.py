"""Mailchimp integration — manage audiences and members."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("mailchimp")


def _base_url(api_key: str) -> str:
    # Mailchimp API keys end with -dc (e.g. xxxxx-us21)
    dc = api_key.split("-")[-1] if "-" in api_key else "us1"
    return f"https://{dc}.api.mailchimp.com/3.0"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def tool_list_audiences() -> str:
    """List all audiences (lists) in the Mailchimp account."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure mailchimp"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(api_key)}/lists",
                headers=_headers(api_key),
                params={"count": 20},
            )
            resp.raise_for_status()
            lists = resp.json().get("lists", [])
            if not lists:
                return "No audiences found."
            lines = []
            for lst in lists:
                members = lst.get("stats", {}).get("member_count", 0)
                lines.append(f"- {lst['name']} (ID: {lst['id']}, {members} members)")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_add_member(list_id: str, email: str, status: str = "subscribed") -> str:
    """Add a member to a Mailchimp audience."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure mailchimp"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(api_key)}/lists/{list_id}/members",
                headers=_headers(api_key),
                json={"email_address": email, "status": status},
            )
            resp.raise_for_status()
            member = resp.json()
            return f"Member added. Email: {member.get('email_address', email)}, Status: {member.get('status', 'N/A')}"
    except Exception as e:
        return f"Error: {e}"
