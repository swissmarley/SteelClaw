# Screenshot Skill

Capture screenshots of web pages by URL.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: screenshot, capture page, webpage screenshot, snapshot url

## System Prompt
You can capture screenshots of web pages using the screenshot_url tool.
Provide a URL and optionally an output path. Uses Playwright for headless browser rendering.
Requires: pip install playwright && playwright install

## Tools

### screenshot_url
Capture a screenshot of a web page.

**Parameters:**
- `url` (string, required): The URL to screenshot
- `output_path` (string, optional): File path to save the screenshot (default: auto-generated in temp directory)
