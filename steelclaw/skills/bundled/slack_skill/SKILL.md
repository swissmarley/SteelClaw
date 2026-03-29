# Slack Integration

Send messages, list channels, and retrieve channel history from Slack workspaces.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: slack, message, channel, chat

## System Prompt
You can interact with Slack workspaces. Use the Slack tools to send messages, list channels, or get channel history. Credentials must be configured via `steelclaw skills configure slack_skill`.

## Tools

### send_message
Send a message to a Slack channel.

**Parameters:**
- `channel` (string, required): Channel ID or name
- `text` (string, required): Message text

### list_channels
List channels in the Slack workspace.

**Parameters:**
- `limit` (integer, optional): Maximum number of channels to return (default 20)

### get_channel_history
Get recent messages from a Slack channel.

**Parameters:**
- `channel` (string, required): Channel ID
- `limit` (integer, optional): Number of messages to retrieve (default 10)
