"""Web search skill — search the web and fetch pages."""

from __future__ import annotations

default_enabled = True
required_credentials = []

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results."""
    import httpx

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20.0),
            headers={
                "User-Agent": _BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": ""},
            )
            resp.raise_for_status()
            html = resp.text

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
    import re
    from urllib.parse import unquote

    results = []

    # Primary pattern: result__a + result__snippet
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )

    # Fallback pattern: broader result block extraction
    if not blocks:
        blocks = re.findall(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</(?:a|div)',
            html,
            re.DOTALL,
        )

    # Second fallback: look for any result links
    if not blocks:
        link_blocks = re.findall(
            r'<a[^>]+class="[^"]*result[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        blocks = [(url, title, "") for url, title in link_blocks]

    for url, title, snippet in blocks:
        if len(results) >= max_results:
            break
        title = re.sub(r"<[^>]+>", "", title).strip()
        snippet = re.sub(r"<[^>]+>", "", snippet).strip()
        # Skip DuckDuckGo ads (contain ad tracking URLs)
        if "ad_provider" in url or "ad_domain" in url or "y.js?" in url:
            continue
        if "uddg=" in url:
            url_match = re.search(r"uddg=([^&]+)", url)
            if url_match:
                url = unquote(url_match.group(1))
        if title and url:
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
