"""Salesforce REST API integration — query, create, and retrieve records."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("salesforce")


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _base_url(instance_url: str) -> str:
    return f"{instance_url.rstrip('/')}/services/data/v59.0"


async def tool_query(soql: str) -> str:
    """Execute a SOQL query against Salesforce."""
    config = _config()
    api_key = config.get("api_key", "")
    instance_url = config.get("instance_url", "")
    if not api_key or not instance_url:
        return "Error: api_key and instance_url must be configured. Run: steelclaw skills configure salesforce"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(instance_url)}/query",
                headers=_headers(api_key),
                params={"q": soql},
            )
            resp.raise_for_status()
            data = resp.json()
            records = data.get("records", [])
            total = data.get("totalSize", 0)
            if not records:
                return "No records found."
            lines = [f"Total records: {total}"]
            for rec in records:
                attrs = rec.get("attributes", {})
                obj_type = attrs.get("type", "Unknown")
                rec_id = rec.get("Id", "N/A")
                name = rec.get("Name", rec.get("Id", "N/A"))
                lines.append(f"- [{obj_type}] {rec_id}: {name}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_record(object_type: str, data: str) -> str:
    """Create a new record in Salesforce. Data should be a JSON string of field-value pairs."""
    config = _config()
    api_key = config.get("api_key", "")
    instance_url = config.get("instance_url", "")
    if not api_key or not instance_url:
        return "Error: api_key and instance_url must be configured. Run: steelclaw skills configure salesforce"
    try:
        payload = json.loads(data) if isinstance(data, str) else data
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(instance_url)}/sobjects/{object_type}",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
            record_id = result.get("id", "N/A")
            return f"Record created. Type: {object_type}, ID: {record_id}"
    except json.JSONDecodeError:
        return "Error: data must be a valid JSON string of field-value pairs."
    except Exception as e:
        return f"Error: {e}"


async def tool_get_record(object_type: str, record_id: str) -> str:
    """Retrieve a specific record from Salesforce by type and ID."""
    config = _config()
    api_key = config.get("api_key", "")
    instance_url = config.get("instance_url", "")
    if not api_key or not instance_url:
        return "Error: api_key and instance_url must be configured. Run: steelclaw skills configure salesforce"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(instance_url)}/sobjects/{object_type}/{record_id}",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            record = resp.json()
            lines = [f"Record: {object_type} / {record_id}"]
            for key, value in record.items():
                if key == "attributes":
                    continue
                lines.append(f"  {key}: {value}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
