# Cron Manager

Schedule, list, and manage recurring tasks using the SteelClaw task engine.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: cron, schedule, reminder, timer

## System Prompt
You can manage scheduled tasks using the cron manager. Schedule recurring actions, list existing jobs, or cancel scheduled tasks.

## Tools

### schedule_task
Schedule a new recurring task.

**Parameters:**
- `cron_expression` (string, required): Cron expression (e.g. "0 9 * * *" for daily at 9am)
- `description` (string, required): Human-readable description of the task
- `action` (string, required): The action to perform (message to send to the agent)

### list_scheduled
List all currently scheduled tasks.

### cancel_task
Cancel a scheduled task by its ID.

**Parameters:**
- `task_id` (string, required): The task ID to cancel
