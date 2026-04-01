"""Headless browser automation via Playwright."""

from __future__ import annotations

import logging

logger = logging.getLogger("steelclaw.skills.browser")

_playwright_available = False
try:
    from playwright.async_api import async_playwright  # noqa: F401
    _playwright_available = True
except ImportError:
    pass


def _check_playwright():
    if not _playwright_available:
        return "Error: Playwright not installed. Run: pip install steelclaw[browser] && playwright install chromium"
    return None


async def tool_browse_url(url: str) -> str:
    """Visit a URL and return the page content."""
    err = _check_playwright()
    if err:
        return err

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            title = await page.title()
            text = await page.inner_text("body")
            await browser.close()
            # Truncate to avoid huge outputs
            if len(text) > 5000:
                text = text[:5000] + "\n...(truncated)"
            return f"Title: {title}\n\n{text}"
    except Exception as e:
        return f"Error browsing {url}: {e}"


async def tool_screenshot(url: str, output_path: str = "/tmp/screenshot.png") -> str:
    """Take a screenshot of a web page."""
    err = _check_playwright()
    if err:
        return err

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()
            return f"Screenshot saved to {output_path}"
    except Exception as e:
        return f"Error taking screenshot: {e}"


async def tool_extract_text(url: str) -> str:
    """Extract all visible text from a web page."""
    err = _check_playwright()
    if err:
        return err

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            text = await page.inner_text("body")
            await browser.close()
            if len(text) > 10000:
                text = text[:10000] + "\n...(truncated)"
            return text
    except Exception as e:
        return f"Error extracting text: {e}"
