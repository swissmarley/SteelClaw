"""Stripe integration — list charges, create invoices, get balance."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "Stripe Secret Key", "type": "password", "test_url": "https://api.stripe.com/v1/balance"},
]

BASE_URL = "https://api.stripe.com/v1"


def _config() -> dict:
    return get_all_credentials("stripe")


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def tool_list_charges(limit: int = 10) -> str:
    """List recent charges on the Stripe account."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure stripe"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/charges",
                headers=_headers(api_key),
                params={"limit": limit},
            )
            resp.raise_for_status()
            charges = resp.json().get("data", [])
            if not charges:
                return "No charges found."
            lines = []
            for ch in charges:
                amount = ch.get("amount", 0) / 100
                currency = ch.get("currency", "usd").upper()
                status = ch.get("status", "N/A")
                lines.append(f"- {ch['id']}: {amount:.2f} {currency} ({status})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_invoice(customer_id: str, description: str = "") -> str:
    """Create a draft invoice for a Stripe customer."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure stripe"
    try:
        data: dict = {"customer": customer_id}
        if description:
            data["description"] = description
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/invoices",
                headers=_headers(api_key),
                data=data,
            )
            resp.raise_for_status()
            invoice = resp.json()
            return f"Invoice created. ID: {invoice['id']}, Status: {invoice.get('status', 'draft')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_balance() -> str:
    """Get the current Stripe account balance."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure stripe"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/balance",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            balance = resp.json()
            lines = []
            for b in balance.get("available", []):
                amount = b.get("amount", 0) / 100
                currency = b.get("currency", "usd").upper()
                lines.append(f"Available: {amount:.2f} {currency}")
            for b in balance.get("pending", []):
                amount = b.get("amount", 0) / 100
                currency = b.get("currency", "usd").upper()
                lines.append(f"Pending: {amount:.2f} {currency}")
            return "\n".join(lines) if lines else "No balance information available."
    except Exception as e:
        return f"Error: {e}"
