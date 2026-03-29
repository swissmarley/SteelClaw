# Web Scraper

Fetch and parse content from any URL.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: scrape, fetch url, web scrape, get page, download page, extract web

## System Prompt
You can fetch and extract content from web pages. The fetch_url tool retrieves a URL
and strips HTML to return readable text. Optionally provide a CSS selector to extract
specific elements (requires BeautifulSoup). Uses httpx for HTTP requests.

## Tools

### fetch_url
Fetch a URL and return its text content with HTML tags stripped.

**Parameters:**
- `url` (string, required): The URL to fetch
- `selector` (string, optional): CSS selector to extract specific elements (requires beautifulsoup4)
