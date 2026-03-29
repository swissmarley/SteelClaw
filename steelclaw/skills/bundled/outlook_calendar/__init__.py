"""Outlook Calendar skill — manage events via Microsoft Graph API."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://graph.microsoft.com/v1.0/me/events"


def _config() -> dict:
    return get_all_credentials("outlook_calendar")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_list_events(max_results: int = 10) -> str:
    """List upcoming Outlook calendar events."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure outlook_calendar"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                BASE_URL,
                headers=_headers(),
                params={"$top": max_results, "$orderby": "start/dateTime"},
            )
            resp.raise_for_status()
            data = resp.json()
        events = data.get("value", [])
        if not events:
            return "No upcoming events found."
        lines = ["Upcoming Outlook events:\n"]
        for i, ev in enumerate(events, 1):
            start = ev.get("start", {}).get("dateTime", "")
            subject = ev.get("subject", "(No subject)")
            lines.append(f"{i}. **{subject}** — {start} (ID: {ev.get('id', '')[:20]}...)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_event(
    subject: str,
    start_time: str,
    end_time: str,
    body: str = "",
    location: str = "",
) -> str:
    """Create a new Outlook calendar event."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure outlook_calendar"
    payload: dict = {
        "subject": subject,
        "start": {"dateTime": start_time, "timeZone": "UTC"},
        "end": {"dateTime": end_time, "timeZone": "UTC"},
    }
    if body:
        payload["body"] = {"contentType": "Text", "content": body}
    if location:
        payload["location"] = {"displayName": location}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(BASE_URL, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
        return f"Event created: **{data.get('subject')}** (ID: {data.get('id', '')[:20]}...)"
    except Exception as e:
        return f"Error: {e}"
