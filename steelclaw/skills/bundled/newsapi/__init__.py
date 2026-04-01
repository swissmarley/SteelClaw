"""NewsAPI skill — top headlines and news search via NewsAPI."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://newsapi.org/v2"

required_credentials = [
    {"key": "api_key", "label": "NewsAPI Key", "type": "password", "test_url": "https://newsapi.org/v2/top-headlines?country=us&pageSize=1"},
]


def _config() -> dict:
    return get_all_credentials("newsapi")


def _headers() -> dict:
    config = _config()
    api_key = config.get("api_key", "")
    return {"X-Api-Key": api_key}


async def tool_get_headlines(
    country: str = "us", category: str = "", max_results: int = 10
) -> str:
    """Get top headlines from NewsAPI."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure newsapi"
    params: dict = {"country": country, "pageSize": max_results}
    if category:
        params["category"] = category
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/top-headlines", headers=_headers(), params=params
            )
            resp.raise_for_status()
            data = resp.json()
        articles = data.get("articles", [])
        if not articles:
            return "No headlines found."
        lines = ["Top Headlines:\n"]
        for i, a in enumerate(articles, 1):
            lines.append(f"{i}. **{a.get('title', '')}**")
            lines.append(f"   Source: {a.get('source', {}).get('name', '')}")
            lines.append(f"   {a.get('url', '')}")
            if a.get("description"):
                lines.append(f"   {a['description']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_search_news(
    query: str, sort_by: str = "publishedAt", max_results: int = 10
) -> str:
    """Search news articles via NewsAPI."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure newsapi"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/everything",
                headers=_headers(),
                params={"q": query, "sortBy": sort_by, "pageSize": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        articles = data.get("articles", [])
        if not articles:
            return f"No articles found for: {query}"
        lines = [f"News results for: {query}\n"]
        for i, a in enumerate(articles, 1):
            lines.append(f"{i}. **{a.get('title', '')}**")
            lines.append(f"   Source: {a.get('source', {}).get('name', '')} | {a.get('publishedAt', '')}")
            lines.append(f"   {a.get('url', '')}")
            if a.get("description"):
                lines.append(f"   {a['description']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
