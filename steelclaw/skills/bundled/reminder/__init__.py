"""Reminder skill — schedule one-time reminders via the task engine."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("steelclaw.skills.reminder")

# Simple file-based reminder store (works without scheduler dependency)
REMINDERS_FILE = Path("data/reminders.json")


def _load_reminders() -> list[dict]:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if REMINDERS_FILE.exists():
        return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
    return []


def _save_reminders(reminders: list[dict]) -> None:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(reminders, indent=2), encoding="utf-8")


async def tool_set_reminder(message: str, minutes: int) -> str:
    """Schedule a one-time reminder."""
    if minutes < 1:
        return "Reminder must be at least 1 minute from now."

    now = datetime.now(timezone.utc)
    trigger_at = now + timedelta(minutes=minutes)

    reminders = _load_reminders()
    reminder_id = f"rem-{int(now.timestamp())}-{len(reminders)}"

    reminders.append({
        "id": reminder_id,
        "message": message,
        "created_at": now.isoformat(),
        "trigger_at": trigger_at.isoformat(),
        "minutes": minutes,
        "fired": False,
    })
    _save_reminders(reminders)

    time_str = trigger_at.strftime("%H:%M UTC")
    return f"Reminder set: '{message}' in {minutes} minutes (at {time_str}). ID: {reminder_id}"


async def tool_list_reminders() -> str:
    """List all active reminders."""
    reminders = _load_reminders()
    now = datetime.now(timezone.utc)

    active = [r for r in reminders if not r.get("fired")]
    if not active:
        return "No active reminders."

    lines = ["Active reminders:\n"]
    for r in active:
        trigger = datetime.fromisoformat(r["trigger_at"])
        delta = trigger - now
        if delta.total_seconds() > 0:
            mins = int(delta.total_seconds() / 60)
            status = f"in {mins}m"
        else:
            status = "overdue"
        lines.append(f"- **{r['id']}**: {r['message']} ({status})")
    return "\n".join(lines)


async def tool_cancel_reminder(reminder_id: str) -> str:
    """Cancel a scheduled reminder."""
    reminders = _load_reminders()
    for r in reminders:
        if r["id"] == reminder_id:
            r["fired"] = True
            _save_reminders(reminders)
            return f"Reminder cancelled: {reminder_id}"
    return f"Reminder not found: {reminder_id}"
