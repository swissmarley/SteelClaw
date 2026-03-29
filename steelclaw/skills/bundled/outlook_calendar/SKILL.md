# Outlook Calendar

Manage Microsoft Outlook calendar events via Microsoft Graph API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: outlook, microsoft calendar, office 365, outlook events

## System Prompt
You can use Outlook Calendar. Credentials must be configured via `steelclaw skills configure outlook_calendar`.

## Tools

### list_events
List upcoming Outlook calendar events.

**Parameters:**
- `max_results` (integer): Maximum events to return (default: 10)

### create_event
Create a new Outlook calendar event.

**Parameters:**
- `subject` (string, required): Event subject
- `start_time` (string, required): Start time in ISO 8601 format
- `end_time` (string, required): End time in ISO 8601 format
- `body` (string): Event body/description
- `location` (string): Event location
