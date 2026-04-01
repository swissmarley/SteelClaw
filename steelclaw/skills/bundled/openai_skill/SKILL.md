# OpenAI

Access OpenAI API for chat completions and image generation.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: openai, gpt, chatgpt, dall-e, image generation, ai completion

## System Prompt
You can use OpenAI. Credentials must be configured via `steelclaw skills configure openai_skill`.

## Tools

### chat_completion
Send a chat completion request to OpenAI.

**Parameters:**
- `prompt` (string, required): The user message/prompt
- `model` (string): Model to use (default: "gpt-4o")
- `system_prompt` (string): System message
- `max_tokens` (integer): Maximum tokens in response (default: 1024)

### generate_image
Generate an image using DALL-E.

**Parameters:**
- `prompt` (string, required): Image description
- `size` (string): Image size — "1024x1024", "1024x1792", or "1792x1024" (default: "1024x1024")
- `model` (string): Model to use (default: "dall-e-3")
