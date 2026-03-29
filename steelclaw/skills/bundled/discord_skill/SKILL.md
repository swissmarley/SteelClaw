# Discord Integration

Send messages, list channels, and retrieve messages from Discord servers via the Bot API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: discord, bot, server, guild

## System Prompt
You can interact with Discord servers. Use the Discord tools to send messages, list channels, or get messages. Credentials must be configured via `steelclaw skills configure discord_skill`.

## Tools

### send_message
Send a message to a Discord channel.

**Parameters:**
- `channel_id` (string, required): The Discord channel ID
- `content` (string, required): Message content

### list_channels
List channels in a Discord guild/server.

**Parameters:**
- `guild_id` (string, required): The Discord guild (server) ID

### get_messages
Get recent messages from a Discord channel.

**Parameters:**
- `channel_id` (string, required): The Discord channel ID
- `limit` (integer, optional): Number of messages to retrieve (default 10)
