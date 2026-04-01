# Web Search

Search the web and fetch webpage content.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: search, google, web, browse, lookup, find online

## System Prompt
You have full web access via web_search and fetch_url tools.
ALWAYS use web_search when the user asks about current events, real-time data, news, prices, weather, sports scores, or any topic where up-to-date information matters.
After searching, use fetch_url to read the most relevant pages for detailed answers.
Never tell the user you cannot browse the internet. Always cite your sources.

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
