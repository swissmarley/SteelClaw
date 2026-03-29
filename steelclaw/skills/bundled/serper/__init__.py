"""Serper skill — Google Search and image search via Serper API."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://google.serper.dev"


def _config() -> dict:
    return get_all_credentials("serper")


def _headers() -> dict:
    config = _config()
    api_key = config.get("api_key", "")
    return {"X-API-KEY": api_key, "Content-Type": "application/json"}


async def tool_google_search(query: str, num: int = 10) -> str:
    """Search Google via Serper API."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure serper"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/search",
                headers=_headers(),
                json={"q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()
        organic = data.get("organic", [])
        if not organic:
            return f"No results found for: {query}"
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(organic, 1):
            lines.append(f"{i}. **{r.get('title', '')}**")
            lines.append(f"   {r.get('link', '')}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")
        # Include answer box if present
        answer_box = data.get("answerBox")
        if answer_box:
            lines.insert(1, f"**Answer:** {answer_box.get('answer', answer_box.get('snippet', ''))}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_image_search(query: str, num: int = 10) -> str:
    """Search Google Images via Serper API."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure serper"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/images",
                headers=_headers(),
                json={"q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()
        images = data.get("images", [])
        if not images:
            return f"No images found for: {query}"
        lines = [f"Image results for: {query}\n"]
        for i, img in enumerate(images, 1):
            lines.append(f"{i}. **{img.get('title', '')}**")
            lines.append(f"   Image: {img.get('imageUrl', '')}")
            lines.append(f"   Source: {img.get('link', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
