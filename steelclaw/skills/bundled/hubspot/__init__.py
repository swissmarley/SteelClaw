"""HubSpot CRM integration — list, create, and search contacts."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.hubapi.com/crm/v3/objects/contacts"


def _config() -> dict:
    return get_all_credentials("hubspot")


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def tool_list_contacts(limit: int = 10) -> str:
    """List contacts from HubSpot CRM."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure hubspot"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                BASE_URL,
                headers=_headers(api_key),
                params={"limit": limit},
            )
            resp.raise_for_status()
            contacts = resp.json().get("results", [])
            if not contacts:
                return "No contacts found."
            lines = []
            for c in contacts:
                props = c.get("properties", {})
                name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or "Unnamed"
                email = props.get("email", "N/A")
                lines.append(f"- {c['id']}: {name} ({email})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_contact(email: str, firstname: str = "", lastname: str = "") -> str:
    """Create a new contact in HubSpot CRM."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure hubspot"
    try:
        properties: dict = {"email": email}
        if firstname:
            properties["firstname"] = firstname
        if lastname:
            properties["lastname"] = lastname
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                BASE_URL,
                headers=_headers(api_key),
                json={"properties": properties},
            )
            resp.raise_for_status()
            contact = resp.json()
            return f"Contact created. ID: {contact['id']}, Email: {email}"
    except Exception as e:
        return f"Error: {e}"


async def tool_search_contacts(query: str, limit: int = 10) -> str:
    """Search contacts in HubSpot CRM by query string."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure hubspot"
    try:
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                }
            ],
            "limit": limit,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/search",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            contacts = resp.json().get("results", [])
            if not contacts:
                return "No contacts found matching the query."
            lines = []
            for c in contacts:
                props = c.get("properties", {})
                name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or "Unnamed"
                email = props.get("email", "N/A")
                lines.append(f"- {c['id']}: {name} ({email})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
