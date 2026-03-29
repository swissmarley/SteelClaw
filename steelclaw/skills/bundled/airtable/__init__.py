"""Airtable integration — list, create, and retrieve records."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("airtable")


def _base_url(config: dict) -> str:
    base_id = config.get("base_id", "")
    table_name = config.get("table_name", "")
    return f"https://api.airtable.com/v0/{base_id}/{table_name}"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def tool_list_records(max_records: int = 20) -> str:
    """List records from an Airtable table."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure airtable"
    if not config.get("base_id") or not config.get("table_name"):
        return "Error: base_id and table_name must be configured. Run: steelclaw skills configure airtable"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                _base_url(config),
                headers=_headers(api_key),
                params={"maxRecords": max_records},
            )
            resp.raise_for_status()
            records = resp.json().get("records", [])
            if not records:
                return "No records found."
            lines = []
            for rec in records:
                fields_str = json.dumps(rec.get("fields", {}), default=str)[:200]
                lines.append(f"- {rec['id']}: {fields_str}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_record(fields: str) -> str:
    """Create a new record in an Airtable table."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure airtable"
    if not config.get("base_id") or not config.get("table_name"):
        return "Error: base_id and table_name must be configured. Run: steelclaw skills configure airtable"
    try:
        field_data = json.loads(fields)
    except json.JSONDecodeError:
        return "Error: Invalid JSON for fields parameter"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _base_url(config),
                headers=_headers(api_key),
                json={"fields": field_data},
            )
            resp.raise_for_status()
            record = resp.json()
            return f"Record created. ID: {record['id']}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_record(record_id: str) -> str:
    """Retrieve a specific Airtable record by ID."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure airtable"
    if not config.get("base_id") or not config.get("table_name"):
        return "Error: base_id and table_name must be configured. Run: steelclaw skills configure airtable"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(config)}/{record_id}",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            record = resp.json()
            fields_str = json.dumps(record.get("fields", {}), indent=2, default=str)
            return f"Record {record['id']}:\n{fields_str}"
    except Exception as e:
        return f"Error: {e}"
