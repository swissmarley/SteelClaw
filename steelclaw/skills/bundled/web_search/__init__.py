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


# Documentation URL patterns for common libraries
_DOCS_PATTERNS = {
    "python": "https://docs.python.org/3/",
    "flask": "https://flask.palletsprojects.com/",
    "django": "https://docs.djangoproject.com/",
    "fastapi": "https://fastapi.tiangolo.com/",
    "requests": "https://requests.readthedocs.io/",
    "numpy": "https://numpy.org/doc/stable/",
    "pandas": "https://pandas.pydata.org/docs/",
    "react": "https://react.dev/",
    "vue": "https://vuejs.org/guide/",
    "angular": "https://angular.io/docs/",
    "nodejs": "https://nodejs.org/docs/",
    "express": "https://expressjs.com/",
    "typescript": "https://www.typescriptlang.org/docs/",
    "rust": "https://doc.rust-lang.org/",
    "go": "https://go.dev/doc/",
}


async def tool_fetch_docs(library: str, version: str | None = None) -> str:
    """Search official documentation for a library or framework.

    Args:
        library: Library name (e.g., "flask", "react", "pandas")
        version: Specific version to search (optional)

    Returns:
        Documentation search results or link to docs
    """
    library_lower = library.lower().strip()

    # Check if we have a known docs URL
    if library_lower in _DOCS_PATTERNS:
        docs_url = _DOCS_PATTERNS[library_lower]
        if version:
            # Try to construct versioned URL
            docs_url = docs_url.rstrip("/") + f"/{version}/"

        # Fetch the docs page
        result = await tool_fetch_url(docs_url, max_length=3000)
        return f"Documentation for {library}:\n{docs_url}\n\n{result}"

    # Unknown library - search for it
    search_query = f"{library} documentation"
    if version:
        search_query += f" {version}"

    results = await tool_web_search(search_query, max_results=5)

    # Also try common docs URL patterns
    potential_urls = [
        f"https://docs.{library_lower}.io/",
        f"https://{library_lower}.readthedocs.io/",
        f"https://{library_lower}.org/docs/",
        f"https://{library_lower}.com/docs/",
    ]

    intro = f"Searching for {library} documentation...\n\n"
    intro += f"Common docs URLs to try:\n"
    for url in potential_urls:
        intro += f"  - {url}\n"
    intro += "\n"

    return intro + results


async def tool_search_stackoverflow(query: str, max_results: int = 5) -> str:
    """Search Stack Overflow for error messages or programming questions.

    Args:
        query: Search query or error message
        max_results: Maximum results to return

    Returns:
        Stack Overflow search results
    """
    # Use DuckDuckGo with site:stackoverflow.com filter
    so_query = f"site:stackoverflow.com {query}"
    results = await tool_web_search(so_query, max_results=max_results)

    # Format for Stack Overflow context
    intro = f"Stack Overflow results for: {query}\n\n"
    return intro + results


async def tool_read_url(
    url: str,
    selector: str | None = None,
    max_length: int = 10000,
) -> str:
    """Fetch and extract clean text content from a URL.

    Args:
        url: The URL to fetch
        selector: Optional CSS selector to extract specific content
        max_length: Maximum characters to return

    Returns:
        Extracted text content from the URL
    """
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
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        # If selector is provided, try to extract that section
        if selector:
            import re
            # Simple regex-based extraction for common selectors
            # This is a basic implementation - for complex selectors, consider using BeautifulSoup
            pattern = rf'<[^>]*class="[^"]*{re.escape(selector)}[^"]*"[^>]*>(.*?)</'
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            if matches:
                text = " ".join(matches)
            else:
                # Try as ID selector
                pattern = rf'<[^>]*id="{re.escape(selector)}"[^>]*>(.*?)</'
                matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                if matches:
                    text = " ".join(matches)
                else:
                    text = html  # Fall back to full content
        else:
            text = html

        # Strip HTML to plain text
        import re
        # Remove script/style blocks
        text = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", "", text, flags=re.DOTALL)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_length:
            text = text[:max_length] + "... [truncated]"

        return f"Content from {url}:\n\n{text}"
    except Exception as e:
        return f"Read error: {e}"


