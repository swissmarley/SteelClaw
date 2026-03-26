# Web Search

Search the web and fetch webpage content.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: search, google, web, browse, lookup, find online

## System Prompt
You can search the web and fetch webpage content.
Use web_search to find information, then fetch_url to read specific pages.
Always cite your sources when presenting web results.

## Tools

### web_search
Search the web using DuckDuckGo and return results.

**Parameters:**
- `query` (string, required): The search query
- `max_results` (integer): Maximum number of results to return (default: 5)

### fetch_url
Fetch the text content of a webpage.

**Parameters:**
- `url` (string, required): The URL to fetch
- `max_length` (integer): Maximum characters to return (default: 5000)
