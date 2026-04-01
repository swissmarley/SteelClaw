# Telegram Integration

Send messages and retrieve updates from Telegram via the Bot API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: telegram, bot, message, chat

## System Prompt
You can interact with Telegram via a bot. Use the Telegram tools to send messages or get updates. Credentials must be configured via `steelclaw skills configure telegram_skill`.

## Tools

### send_message
Send a message to a Telegram chat.

**Parameters:**
- `chat_id` (string, required): The target chat ID
- `text` (string, required): Message text
- `parse_mode` (string, optional): Parse mode — HTML or MarkdownV2

### get_updates
Get recent updates (messages) sent to the bot.

**Parameters:**
- `limit` (integer, optional): Maximum number of updates to retrieve (default 10)
