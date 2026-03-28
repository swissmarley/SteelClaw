"""Cron/scheduled task management skill — wraps the SteelClaw TaskEngine."""

from __future__ import annotations

import json
import uuid


# Module-level reference to the task engine (set during app startup)
_task_engine = None


def set_task_engine(engine) -> None:
    """Called during app startup to inject the task engine."""
    global _task_engine
    _task_engine = engine


async def tool_schedule_task(cron_expression: str, description: str, action: str) -> str:
    """Schedule a new recurring task."""
    if _task_engine is None:
        return "Error: Task engine not available. Is the scheduler running?"

    if not _task_engine.running:
        return "Error: Scheduler is not running. Enable it in settings."

    job_id = f"user_cron_{uuid.uuid4().hex[:8]}"

    try:
        _task_engine.add_cron_job(
            job_id=job_id,
            func=_scheduled_action,
            cron_expression=cron_expression,
            description=description,
            kwargs={"action": action, "description": description},
        )
        return f"Task scheduled: '{description}' (ID: {job_id}, Cron: {cron_expression})"
    except ValueError as e:
        return f"Error: Invalid cron expression — {e}"
    except Exception as e:
        return f"Error scheduling task: {e}"


async def tool_list_scheduled() -> str:
    """List all currently scheduled tasks."""
    if _task_engine is None:
        return "Error: Task engine not available."

    jobs = _task_engine.list_jobs()
    if not jobs:
        return "No scheduled tasks."

    lines = []
    for j in jobs:
        lines.append(
            f"- {j['id']}: {j.get('description', 'No description')} "
            f"[{j.get('type', '?')}] Next: {j.get('next_run', '?')}"
        )
    return "\n".join(lines)


async def tool_cancel_task(task_id: str) -> str:
    """Cancel a scheduled task by ID."""
    if _task_engine is None:
        return "Error: Task engine not available."

    if _task_engine.remove_job(task_id):
        return f"Task '{task_id}' cancelled."
    return f"Task '{task_id}' not found."


async def _scheduled_action(action: str, description: str) -> None:
    """Callback for scheduled tasks — logs the action."""
    import logging
    logger = logging.getLogger("steelclaw.skills.cron_manager")
    logger.info("Scheduled task fired: %s — %s", description, action)
