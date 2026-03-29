"""Perplexity skill — AI-powered web search via Perplexity API."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

API_URL = "https://api.perplexity.ai/chat/completions"


def _config() -> dict:
    return get_all_credentials("perplexity")


async def tool_search(query: str, model: str = "sonar") -> str:
    """Search the web using Perplexity AI."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure perplexity"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        citations = data.get("citations", [])
        result = content
        if citations:
            result += "\n\n**Sources:**\n"
            for i, url in enumerate(citations, 1):
                result += f"{i}. {url}\n"
        return result
    except Exception as e:
        return f"Error: {e}"
