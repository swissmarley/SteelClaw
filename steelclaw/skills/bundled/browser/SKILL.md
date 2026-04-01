# Browser

Headless browser automation via Playwright — browse URLs, take screenshots, and extract text.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: browse, screenshot, webpage

## System Prompt
You have browser automation capabilities via Playwright. Use the browser tools to visit web pages, take screenshots, or extract text content. Requires `pip install steelclaw[browser]`.

## Tools

### browse_url
Visit a URL and return the page text content.

**Parameters:**
- `url` (string, required): The URL to visit

### screenshot
Take a screenshot of a web page.

**Parameters:**
- `url` (string, required): The URL to screenshot
- `output_path` (string, optional): Where to save the screenshot. Default: /tmp/screenshot.png

### extract_text
Extract all visible text content from a web page.

**Parameters:**
- `url` (string, required): The URL to extract text from
