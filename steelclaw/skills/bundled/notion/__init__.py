"""Notion workspace integration — search, create, and retrieve pages."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "Notion Integration Token", "type": "password", "test_url": "https://api.notion.com/v1/users/me"},
]

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _config() -> dict:
    return get_all_credentials("notion")


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def tool_search_pages(query: str) -> str:
    """Search for pages in Notion by query string."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure notion"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/search",
                headers=_headers(api_key),
                json={"query": query, "page_size": 10},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return "No pages found."
            lines = []
            for r in results:
                title_parts = r.get("properties", {}).get("title", {}).get("title", [])
                title = title_parts[0].get("plain_text", "Untitled") if title_parts else "Untitled"
                lines.append(f"- {title} (ID: {r['id']})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_page(parent_id: str, title: str, content: str = "") -> str:
    """Create a new page in Notion under a parent page or database."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure notion"
    try:
        body: dict = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            },
        }
        if content:
            body["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/pages",
                headers=_headers(api_key),
                json=body,
            )
            resp.raise_for_status()
            page = resp.json()
            return f"Page created. ID: {page['id']}, URL: {page.get('url', 'N/A')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_page(page_id: str) -> str:
    """Retrieve a Notion page by ID."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure notion"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/pages/{page_id}",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            page = resp.json()
            title_parts = page.get("properties", {}).get("title", {}).get("title", [])
            title = title_parts[0].get("plain_text", "Untitled") if title_parts else "Untitled"
            return f"Page: {title}\nID: {page['id']}\nURL: {page.get('url', 'N/A')}\nCreated: {page.get('created_time', 'N/A')}"
    except Exception as e:
        return f"Error: {e}"
