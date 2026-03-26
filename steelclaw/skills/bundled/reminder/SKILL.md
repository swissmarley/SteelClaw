# Reminder

Set reminders and manage time-based notifications.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: remind, reminder, timer, alarm, schedule, in, at

## System Prompt
You can set reminders for the user using the scheduler.
Parse natural time references and create appropriate scheduled tasks.
Confirm the reminder time with the user.

## Tools

### set_reminder
Schedule a one-time reminder.

**Parameters:**
- `message` (string, required): The reminder message
- `minutes` (integer, required): Minutes from now to trigger the reminder

### list_reminders
List all active reminders.

### cancel_reminder
Cancel a scheduled reminder.

**Parameters:**
- `reminder_id` (string, required): The ID of the reminder to cancel
