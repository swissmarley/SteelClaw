"""Google Calendar skill — manage calendar events via Google Calendar API."""

from __future__ import annotations

import httpx
from datetime import datetime, timezone

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "Google API Key", "type": "password", "test_url": None},
    {"key": "client_id", "label": "OAuth Client ID", "type": "text", "test_url": None},
]

BASE_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _config() -> dict:
    return get_all_credentials("google_calendar")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_list_events(max_results: int = 10, time_min: str = "") -> str:
    """List upcoming Google Calendar events."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_calendar"
    if not time_min:
        time_min = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                BASE_URL,
                headers=_headers(),
                params={
                    "maxResults": max_results,
                    "timeMin": time_min,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        events = data.get("items", [])
        if not events:
            return "No upcoming events found."
        lines = ["Upcoming events:\n"]
        for i, ev in enumerate(events, 1):
            start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", ""))
            summary = ev.get("summary", "(No title)")
            lines.append(f"{i}. **{summary}** — {start} (ID: {ev.get('id', '')})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
) -> str:
    """Create a new Google Calendar event."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_calendar"
    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "UTC"},
        "end": {"dateTime": end_time, "timeZone": "UTC"},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(BASE_URL, headers=_headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
        return f"Event created: **{data.get('summary')}** (ID: {data.get('id')})\nLink: {data.get('htmlLink', '')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_delete_event(event_id: str) -> str:
    """Delete a Google Calendar event by ID."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_calendar"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{BASE_URL}/{event_id}", headers=_headers())
            resp.raise_for_status()
        return f"Event {event_id} deleted successfully."
    except Exception as e:
        return f"Error: {e}"
