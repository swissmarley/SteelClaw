# Task Planner

Break down complex tasks into manageable steps with dependency tracking.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: plan, tasks, steps, breakdown, organize, task list

## System Prompt
You can break down complex requests into ordered steps with clear dependencies.
Mark steps as parallel when they don't depend on each other.
Track completion status and re-plan when steps fail.
Always show progress to the user so they understand what's happening.

## Tools

### create_plan
Create a structured plan from a goal with ordered steps.

**Parameters:**
- `goal` (string, required): The high-level goal to accomplish
- `steps` (array, required): List of step objects with description, parallel flag, and depends_on

### update_step
Update a step's status in an active plan.

**Parameters:**
- `plan_id` (string, required): Plan identifier returned by create_plan
- `step_id` (string, required): Step identifier to update
- `status` (string, required): New status - "pending", "in_progress", "completed", "failed"
- `notes` (string): Optional notes about the step execution

### get_plan
Retrieve the current status of a plan.

**Parameters:**
- `plan_id` (string, required): Plan identifier to retrieve

### list_plans
List all active plans.

**Parameters:**
- `active_only` (boolean): Only show plans with pending steps (default: true)