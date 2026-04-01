# Google Calendar

Manage Google Calendar events — list, create, and delete events.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: calendar, google calendar, events, schedule, meeting

## System Prompt
You can use Google Calendar. Credentials must be configured via `steelclaw skills configure google_calendar`.

## Tools

### list_events
List upcoming calendar events.

**Parameters:**
- `max_results` (integer): Maximum events to return (default: 10)
- `time_min` (string): Start time in RFC3339 format (default: now)

### create_event
Create a new calendar event.

**Parameters:**
- `summary` (string, required): Event title
- `start_time` (string, required): Start time in RFC3339 format
- `end_time` (string, required): End time in RFC3339 format
- `description` (string): Event description
- `location` (string): Event location

### delete_event
Delete a calendar event by ID.

**Parameters:**
- `event_id` (string, required): The event ID to delete
