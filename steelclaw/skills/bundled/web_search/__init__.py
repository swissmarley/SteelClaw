"""Web search skill — search the web and fetch pages."""

from __future__ import annotations


async def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML scraping."""
    import httpx

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SteelClaw/1.0)"},
        ) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            resp.raise_for_status()
            html = resp.text

        # Parse results from DuckDuckGo HTML
        results = _parse_ddg_html(html, max_results)
        if not results:
            return f"No results found for: {query}"

        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**")
            lines.append(f"   {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")
        return "\n".join(lines)

    except Exception as e:
        return f"Search error: {e}"


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Parse DuckDuckGo HTML results page."""
    results = []
    # Simple parsing — find result links and snippets
    import re

    # Each result is in a <div class="result"> or similar
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    for url, title, snippet in blocks[:max_results]:
        # Clean HTML tags
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        # DuckDuckGo wraps URLs in a redirect
        if "uddg=" in url:
            url_match = re.search(r"uddg=([^&]+)", url)
            if url_match:
                from urllib.parse import unquote
                url = unquote(url_match.group(1))
        results.append({"title": title, "url": url, "snippet": snippet})

    return results


async def tool_fetch_url(url: str, max_length: int = 5000) -> str:
    """Fetch a webpage and return its text content."""
    import httpx

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SteelClaw/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        # Strip HTML to plain text
        import re
        # Remove script/style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_length:
            text = text[:max_length] + "... [truncated]"

        return f"Content from {url}:\n\n{text}"
    except Exception as e:
        return f"Fetch error: {e}"
