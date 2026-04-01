# Serper

Google Search and image search via Serper API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: serper, google search, search, image search, serp

## System Prompt
You can use Serper. Credentials must be configured via `steelclaw skills configure serper`.

## Tools

### google_search
Search Google via Serper API.

**Parameters:**
- `query` (string, required): Search query
- `num` (integer): Number of results (default: 10)

### image_search
Search Google Images via Serper API.

**Parameters:**
- `query` (string, required): Image search query
- `num` (integer): Number of results (default: 10)
