"""Web Scraper skill — fetch and parse content from URLs."""

from __future__ import annotations

import re


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities using regex."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def tool_fetch_url(url: str, selector: str | None = None) -> str:
    """Fetch a URL and return its text content."""
    try:
        try:
            import httpx
        except ImportError:
            return (
                "Error: httpx is not installed. "
                "Install it with: pip install httpx"
            )

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SteelClaw/1.0)"
            })
            response.raise_for_status()

        html = response.text
        content_type = response.headers.get("content-type", "")

        # If not HTML, return raw text
        if "html" not in content_type and "xml" not in content_type:
            return f"[{response.status_code}] Content-Type: {content_type}\n\n{html[:5000]}"

        # If selector provided, try BeautifulSoup
        if selector:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                elements = soup.select(selector)
                if not elements:
                    return f"No elements matched selector: {selector}"
                results = []
                for el in elements[:50]:
                    results.append(el.get_text(separator=" ", strip=True))
                return f"Found {len(elements)} element(s) matching '{selector}':\n\n" + "\n---\n".join(results)
            except ImportError:
                return (
                    "Error: beautifulsoup4 is required for CSS selectors. "
                    "Install it with: pip install beautifulsoup4\n\n"
                    "Returning full page text instead:\n\n" + _strip_html(html)[:5000]
                )

        # Default: strip HTML with regex
        text = _strip_html(html)
        if len(text) > 5000:
            text = text[:5000] + "\n\n... (truncated)"

        return f"[{response.status_code}] {url}\n\n{text}"
    except Exception as e:
        return f"Error fetching URL: {e}"
