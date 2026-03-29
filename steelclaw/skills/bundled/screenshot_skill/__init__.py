"""Screenshot skill — capture web page screenshots using Playwright."""

from __future__ import annotations

import os
import tempfile
import time


async def tool_screenshot_url(url: str, output_path: str | None = None) -> str:
    """Capture a screenshot of a web page."""
    try:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return (
                "Error: playwright is not installed. "
                "Install it with: pip install playwright && playwright install"
            )

        if not output_path:
            timestamp = int(time.time())
            output_path = os.path.join(tempfile.gettempdir(), f"screenshot_{timestamp}.png")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()

        file_size = os.path.getsize(output_path)
        return (
            f"Screenshot saved to: {output_path}\n"
            f"File size: {file_size:,} bytes\n"
            f"URL: {url}"
        )
    except Exception as e:
        return f"Error capturing screenshot: {e}"
