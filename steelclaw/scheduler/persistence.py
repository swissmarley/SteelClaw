"""Schedule persistence — saves/loads triggers to ~/.steelclaw/schedules.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("steelclaw.scheduler.persistence")

SCHEDULES_PATH = Path.home() / ".steelclaw" / "schedules.json"


def load_schedules() -> list[dict[str, Any]]:
    """Load all persisted schedules from disk."""
    if not SCHEDULES_PATH.exists():
        return []
    try:
        return json.loads(SCHEDULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read schedules.json")
        return []


def save_schedules(schedules: list[dict[str, Any]]) -> None:
    """Persist all schedules to disk."""
    SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULES_PATH.write_text(
        json.dumps(schedules, indent=2, default=str), encoding="utf-8"
    )


def add_schedule(schedule: dict[str, Any]) -> None:
    """Add or replace a schedule by ID."""
    schedules = load_schedules()
    schedules = [s for s in schedules if s.get("id") != schedule.get("id")]
    schedules.append(schedule)
    save_schedules(schedules)


def remove_schedule(schedule_id: str) -> bool:
    """Remove a schedule by ID. Returns True if found and removed."""
    schedules = load_schedules()
    filtered = [s for s in schedules if s.get("id") != schedule_id]
    if len(filtered) == len(schedules):
        return False
    save_schedules(filtered)
    return True


def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    """Get a single schedule by ID."""
    for s in load_schedules():
        if s.get("id") == schedule_id:
            return s
    return None


def update_schedule_field(schedule_id: str, field: str, value: Any) -> bool:
    """Update a single field on a schedule."""
    schedules = load_schedules()
    for s in schedules:
        if s.get("id") == schedule_id:
            s[field] = value
            save_schedules(schedules)
            return True
    return False
