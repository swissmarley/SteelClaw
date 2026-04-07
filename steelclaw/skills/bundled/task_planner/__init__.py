"""Task planner skill — break down complex tasks into manageable steps."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# In-memory plan storage (plans persist only during session)
_plans: dict[str, "Plan"] = {}


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
) -> str:
    """Create a structured plan from a goal.

    Args:
        goal: The high-level goal to accomplish
        steps: List of step dictionaries with description, parallel, depends_on

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
    )

    _plans[plan_id] = plan

    return f"Created plan: {plan_id}\n\n{_format_plan(plan)}"


async def tool_update_step(
    plan_id: str,
    step_id: str,
    status: str,
    notes: str | None = None,
) -> str:
    """Update a step's status in an active plan.

    Args:
        plan_id: Plan identifier
        step_id: Step identifier to update
        status: New status - "pending", "in_progress", "completed", "failed"
        notes: Optional notes about execution

    Returns:
        Updated plan status
    """
    if plan_id not in _plans:
        return f"Error: Plan {plan_id} not found"

    plan = _plans[plan_id]

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


async def tool_get_plan(plan_id: str) -> str:
    """Retrieve the current status of a plan.

    Args:
        plan_id: Plan identifier

    Returns:
        Plan details and step statuses
    """
    if plan_id not in _plans:
        return f"Error: Plan {plan_id} not found"

    plan = _plans[plan_id]
    return _format_plan(plan)


async def tool_list_plans(active_only: bool = True) -> str:
    """List all active plans.

    Args:
        active_only: Only show plans with pending steps

    Returns:
        List of plans
    """
    if not _plans:
        return "No plans found. Use create_plan to create one."

    lines = ["Plans:", ""]

    for plan_id, plan in _plans.items():
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