"""Supabase skill — interact with Supabase REST API."""

from __future__ import annotations

import json
import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("supabase")


def _base_url() -> str:
    config = _config()
    project_id = config.get("project_id", "")
    return f"https://{project_id}.supabase.co/rest/v1"


def _headers() -> dict:
    config = _config()
    api_key = config.get("api_key", "")
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def tool_query_table(
    table: str, select: str = "*", filters: str = "", limit: int = 50
) -> str:
    """Query rows from a Supabase table."""
    config = _config()
    if not config.get("api_key") or not config.get("project_id"):
        return "Error: Supabase credentials not configured. Run: steelclaw skills configure supabase"
    url = f"{_base_url()}/{table}"
    params: dict = {"select": select, "limit": limit}
    if filters:
        for f in filters.split("&"):
            if "=" in f:
                key, val = f.split("=", 1)
                params[key] = val
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return f"No rows found in {table}."
        return f"Results from **{table}** ({len(data)} rows):\n```json\n{json.dumps(data, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"


async def tool_insert_row(table: str, data: str) -> str:
    """Insert a row into a Supabase table."""
    config = _config()
    if not config.get("api_key") or not config.get("project_id"):
        return "Error: Supabase credentials not configured. Run: steelclaw skills configure supabase"
    try:
        row_data = json.loads(data)
    except json.JSONDecodeError:
        return "Error: Invalid JSON data."
    url = f"{_base_url()}/{table}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=_headers(), json=row_data)
            resp.raise_for_status()
            result = resp.json()
        return f"Inserted into **{table}**:\n```json\n{json.dumps(result, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"


async def tool_delete_row(table: str, filters: str) -> str:
    """Delete rows from a Supabase table."""
    config = _config()
    if not config.get("api_key") or not config.get("project_id"):
        return "Error: Supabase credentials not configured. Run: steelclaw skills configure supabase"
    url = f"{_base_url()}/{table}"
    params: dict = {}
    for f in filters.split("&"):
        if "=" in f:
            key, val = f.split("=", 1)
            params[key] = val
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(url, headers=_headers(), params=params)
            resp.raise_for_status()
            result = resp.json()
        return f"Deleted from **{table}**:\n```json\n{json.dumps(result, indent=2, default=str)}\n```"
    except Exception as e:
        return f"Error: {e}"
