# Web Search

Search the web and fetch webpage content.

## Metadata
- version: 1.1.0
- author: SteelClaw
- triggers: search, google, web, browse, lookup, find online, docs, stackoverflow

## System Prompt
You have full web access via web_search and fetch_url tools.
ALWAYS use web_search when the user asks about current events, real-time data, news, prices, weather, sports scores, or any topic where up-to-date information matters.
After searching, use fetch_url to read the most relevant pages for detailed answers.
Never tell the user you cannot browse the internet. Always cite your sources.

When encountering an unfamiliar library or API, use fetch_docs or search_stackoverflow
to find documentation before assuming behavior. Proactive documentation search leads to
better, more accurate implementations.

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

### fetch_docs
Search official documentation for a library or framework.

**Parameters:**
- `library` (string, required): Library name (e.g., "flask", "react", "pandas")
- `version` (string): Specific version to search (optional)

### search_stackoverflow
Search Stack Overflow for error messages or programming questions.

**Parameters:**
- `query` (string, required): Search query or error message
- `max_results` (integer): Maximum results to return (default: 5)

### read_url
Fetch and extract clean text content from a URL, with optional CSS selector.

**Parameters:**
- `url` (string, required): The URL to fetch
- `selector` (string): CSS selector to extract specific content (optional)
- `max_length` (integer): Maximum characters to return (default: 10000)
