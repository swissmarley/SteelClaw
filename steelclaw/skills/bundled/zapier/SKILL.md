# Zapier Integration

Trigger Zapier zaps via webhook URLs.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: zapier, zap, automation, webhook

## System Prompt
You can trigger Zapier zaps via webhooks. Use the Zapier tool to fire automation workflows with optional data payloads. Credentials must be configured via `steelclaw skills configure zapier`.

## Tools

### trigger_zap
Trigger a Zapier webhook with an optional JSON payload.

**Parameters:**
- `payload` (string, optional): JSON payload to send with the webhook
