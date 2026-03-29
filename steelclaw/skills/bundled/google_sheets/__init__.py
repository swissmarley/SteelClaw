"""Google Sheets integration — read, write, and list sheets."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"


def _config() -> dict:
    return get_all_credentials("google_sheets")


async def tool_read_range(spreadsheet_id: str, range: str) -> str:
    """Read data from a range in a Google Sheets spreadsheet."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure google_sheets"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/{spreadsheet_id}/values/{range}",
                params={"key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            values = data.get("values", [])
            if not values:
                return "No data found in the specified range."
            lines = []
            for row in values:
                lines.append("\t".join(str(cell) for cell in row))
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_write_range(spreadsheet_id: str, range: str, values: str) -> str:
    """Write data to a range in a Google Sheets spreadsheet."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure google_sheets"
    try:
        parsed_values = json.loads(values)
    except json.JSONDecodeError:
        return "Error: Invalid JSON for values parameter. Must be an array of arrays."
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{BASE_URL}/{spreadsheet_id}/values/{range}",
                params={"key": api_key, "valueInputOption": "USER_ENTERED"},
                json={"values": parsed_values},
            )
            resp.raise_for_status()
            result = resp.json()
            return f"Updated {result.get('updatedCells', 0)} cells in {result.get('updatedRange', range)}"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_sheets(spreadsheet_id: str) -> str:
    """List all sheets in a Google Sheets spreadsheet."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure google_sheets"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/{spreadsheet_id}",
                params={"key": api_key, "fields": "sheets.properties"},
            )
            resp.raise_for_status()
            sheets = resp.json().get("sheets", [])
            if not sheets:
                return "No sheets found."
            lines = []
            for s in sheets:
                props = s.get("properties", {})
                lines.append(f"- {props.get('title', 'Untitled')} (ID: {props.get('sheetId', 'N/A')}, Index: {props.get('index', 'N/A')})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
