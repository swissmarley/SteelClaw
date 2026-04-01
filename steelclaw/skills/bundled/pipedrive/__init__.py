"""Pipedrive integration — list, create, and retrieve deals."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.pipedrive.com/v1"

required_credentials = [
    {"key": "api_token", "label": "Pipedrive API Token", "type": "password"},
]


def _config() -> dict:
    return get_all_credentials("pipedrive")


async def tool_list_deals(limit: int = 10) -> str:
    """List deals from Pipedrive."""
    config = _config()
    api_token = config.get("api_token", "")
    if not api_token:
        return "Error: API token not configured. Run: steelclaw skills configure pipedrive"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/deals",
                params={"api_token": api_token, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            deals = data.get("data") or []
            if not deals:
                return "No deals found."
            lines = []
            for d in deals:
                title = d.get("title", "Untitled")
                value = d.get("value", 0)
                currency = d.get("currency", "USD")
                status = d.get("status", "N/A")
                lines.append(f"- {d['id']}: {title} ({value} {currency}) [{status}]")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_deal(title: str, value: float = 0, currency: str = "USD", person_id: int = 0) -> str:
    """Create a new deal in Pipedrive."""
    config = _config()
    api_token = config.get("api_token", "")
    if not api_token:
        return "Error: API token not configured. Run: steelclaw skills configure pipedrive"
    try:
        payload: dict = {"title": title}
        if value:
            payload["value"] = value
        if currency:
            payload["currency"] = currency
        if person_id:
            payload["person_id"] = person_id
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/deals",
                params={"api_token": api_token},
                json=payload,
            )
            resp.raise_for_status()
            deal = resp.json().get("data", {})
            return f"Deal created. ID: {deal.get('id', 'N/A')}, Title: {title}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_deal(deal_id: int) -> str:
    """Retrieve a specific deal from Pipedrive by ID."""
    config = _config()
    api_token = config.get("api_token", "")
    if not api_token:
        return "Error: API token not configured. Run: steelclaw skills configure pipedrive"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/deals/{deal_id}",
                params={"api_token": api_token},
            )
            resp.raise_for_status()
            deal = resp.json().get("data", {})
            if not deal:
                return f"Deal {deal_id} not found."
            title = deal.get("title", "Untitled")
            value = deal.get("value", 0)
            currency = deal.get("currency", "USD")
            status = deal.get("status", "N/A")
            stage = deal.get("stage_id", "N/A")
            owner = deal.get("owner_name", "N/A")
            return (
                f"Deal: {deal.get('id')}\n"
                f"Title: {title}\n"
                f"Value: {value} {currency}\n"
                f"Status: {status}\n"
                f"Stage ID: {stage}\n"
                f"Owner: {owner}"
            )
    except Exception as e:
        return f"Error: {e}"
