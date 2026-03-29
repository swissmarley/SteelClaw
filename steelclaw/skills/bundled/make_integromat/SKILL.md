# Make (Integromat) Integration

Trigger Make.com scenarios via webhook URLs.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: make, integromat, scenario, automation

## System Prompt
You can trigger Make.com (Integromat) scenarios via webhooks. Use the Make tool to fire automation scenarios with optional data payloads. Credentials must be configured via `steelclaw skills configure make_integromat`.

## Tools

### trigger_scenario
Trigger a Make.com scenario webhook with an optional JSON payload.

**Parameters:**
- `payload` (string, optional): JSON payload to send with the webhook
