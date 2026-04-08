"""Task planner skill — break down complex tasks into manageable steps.

NOTE: This implementation uses session-scoped in-memory storage. Plans are
isolated by session_id to prevent data leakage between users. For production
use with persistent storage, consider integrating with a database backend.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

# Session-scoped plan storage: {session_id: {plan_id: Plan}}
# This prevents data leakage between different users/sessions
_session_plans: dict[str, dict[str, "Plan"]] = {}

# Track last-access time per session to enable TTL-based eviction
_session_last_access: dict[str, datetime] = {}

# Sessions unused for longer than this are evicted from memory
_SESSION_TTL = timedelta(hours=2)

# Lock protecting both _session_plans and _session_last_access
_plans_lock = threading.Lock()


def _evict_stale_sessions() -> None:
    """Remove sessions that have not been accessed within the TTL window.

    Must be called with _plans_lock held.
    Iterates over a static copy of items to avoid RuntimeError from
    concurrent modification of the dict.
    """
    cutoff = datetime.now() - _SESSION_TTL
    stale = [sid for sid, ts in list(_session_last_access.items()) if ts < cutoff]
    for sid in stale:
        _session_plans.pop(sid, None)
        _session_last_access.pop(sid, None)


def _get_session_plans(session_id: str) -> dict[str, "Plan"]:
    """Get or create the plan storage for a session, evicting stale sessions."""
    with _plans_lock:
        _evict_stale_sessions()
        if session_id not in _session_plans:
            _session_plans[session_id] = {}
        _session_last_access[session_id] = datetime.now()
        return _session_plans[session_id]


@dataclass
class Step:
    """A single step in a plan."""

    id: str
    description: str
    parallel: bool = False
    depends_on: list[str] = field(default_factory=list)
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Plan:
    """A task plan with steps."""

    id: str
    goal: str
    steps: list[Step]
    created_at: datetime
    session_id: str = "default"  # Scope plans to a session
    status: Literal["active", "completed", "failed"] = "active"


def _generate_id() -> str:
    """Generate a unique plan/step ID."""
    return uuid.uuid4().hex[:8]


def _format_plan(plan: Plan) -> str:
    """Format a plan for display."""
    lines = [f"Plan: {plan.goal}"]
    lines.append(f"ID: {plan.id}")
    lines.append(f"Status: {plan.status}")
    lines.append(f"Created: {plan.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("Steps:")

    # Build dependency graph for display
    for step in plan.steps:
        status_icon = {
            "pending": "○",
            "in_progress": "◐",
            "completed": "●",
            "failed": "✗",
        }.get(step.status, "○")

        deps = f" (depends: {', '.join(step.depends_on)})" if step.depends_on else ""
        parallel_marker = " [parallel]" if step.parallel else ""
        notes = f"\n    Notes: {step.notes}" if step.notes else ""

        lines.append(f"  {status_icon} [{step.id}] {step.description}{deps}{parallel_marker}{notes}")

    return "\n".join(lines)


async def tool_create_plan(
    goal: str,
    steps: list[dict],
    session_id: str = "default",
) -> str:
    """Create a structured plan from a goal.

    Args:
        goal: The high-level goal to accomplish
        steps: List of step dictionaries with description, parallel, depends_on
        session_id: Session identifier for plan isolation (prevents data leakage)

    Returns:
        Plan ID and formatted plan
    """
    plan_id = _generate_id()
    step_objects = []

    for i, step_data in enumerate(steps):
        step_id = step_data.get("id", f"step_{i + 1}")
        if step_id.startswith("step_"):
            # Auto-generate short IDs
            step_id = f"s{i + 1}"

        step = Step(
            id=step_id,
            description=step_data.get("description", f"Step {i + 1}"),
            parallel=step_data.get("parallel", False),
            depends_on=step_data.get("depends_on", []),
        )
        step_objects.append(step)

    plan = Plan(
        id=plan_id,
        goal=goal,
        steps=step_objects,
        created_at=datetime.now(),
        session_id=session_id,
    )

    plans = _get_session_plans(session_id)
    plans[plan_id] = plan

    return f"Created plan: {plan_id}\n\n{_format_plan(plan)}"


async def tool_update_step(
    plan_id: str,
    step_id: str,
    status: str,
    notes: str | None = None,
    session_id: str = "default",
) -> str:
    """Update a step's status in an active plan.

    Args:
        plan_id: Plan identifier
        step_id: Step identifier to update
        status: New status - "pending", "in_progress", "completed", "failed"
        notes: Optional notes about execution
        session_id: Session identifier for plan isolation

    Returns:
        Updated plan status
    """
    plans = _get_session_plans(session_id)

    if plan_id not in plans:
        return f"Error: Plan {plan_id} not found"

    plan = plans[plan_id]

    # Find the step
    step = None
    for s in plan.steps:
        if s.id == step_id:
            step = s
            break

    if not step:
        return f"Error: Step {step_id} not found in plan {plan_id}"

    # Update status
    valid_statuses = ["pending", "in_progress", "completed", "failed"]
    if status not in valid_statuses:
        return f"Error: Invalid status '{status}'. Must be one of: {valid_statuses}"

    step.status = status
    if notes:
        step.notes = notes

    if status == "in_progress":
        step.started_at = datetime.now()
    elif status in ("completed", "failed"):
        step.completed_at = datetime.now()

    # Check if all steps are completed
    all_completed = all(s.status == "completed" for s in plan.steps)
    any_failed = any(s.status == "failed" for s in plan.steps)

    if any_failed:
        plan.status = "failed"
    elif all_completed:
        plan.status = "completed"

    return f"Updated step {step_id} to {status}\n\n{_format_plan(plan)}"


async def tool_get_plan(
    plan_id: str,
    session_id: str = "default",
) -> str:
    """Retrieve the current status of a plan.

    Args:
        plan_id: Plan identifier
        session_id: Session identifier for plan isolation

    Returns:
        Plan details and step statuses
    """
    plans = _get_session_plans(session_id)

    if plan_id not in plans:
        return f"Error: Plan {plan_id} not found"

    plan = plans[plan_id]
    return _format_plan(plan)


async def tool_list_plans(
    active_only: bool = True,
    session_id: str = "default",
) -> str:
    """List all active plans for the current session.

    Args:
        active_only: Only show plans with pending steps
        session_id: Session identifier for plan isolation

    Returns:
        List of plans
    """
    plans = _get_session_plans(session_id)

    if not plans:
        return "No plans found. Use create_plan to create one."

    lines = ["Plans:", ""]

    for plan_id, plan in plans.items():
        if active_only and plan.status != "active":
            continue

        pending = sum(1 for s in plan.steps if s.status == "pending")
        in_progress = sum(1 for s in plan.steps if s.status == "in_progress")
        completed = sum(1 for s in plan.steps if s.status == "completed")
        failed = sum(1 for s in plan.steps if s.status == "failed")

        status_icon = "●" if plan.status == "completed" else "◐" if plan.status == "active" else "✗"
        lines.append(
            f"  {status_icon} [{plan_id}] {plan.goal} "
            f"({completed}/{len(plan.steps)} done, {in_progress} in progress, {pending} pending, {failed} failed)"
        )

    if len(lines) == 2:
        return "No active plans found."

    return "\n".join(lines)