"""Shopify integration — list products, list orders, get order details."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

API_VERSION = "2024-01"


def _config() -> dict:
    return get_all_credentials("shopify")


def _base_url(store: str) -> str:
    return f"https://{store}.myshopify.com/admin/api/{API_VERSION}"


def _headers(access_token: str) -> dict:
    return {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}


async def tool_list_products(limit: int = 20) -> str:
    """List products from the Shopify store."""
    config = _config()
    access_token = config.get("access_token", "")
    store = config.get("store", "")
    if not access_token or not store:
        return "Error: access_token and store must be configured. Run: steelclaw skills configure shopify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(store)}/products.json",
                headers=_headers(access_token),
                params={"limit": limit},
            )
            resp.raise_for_status()
            products = resp.json().get("products", [])
            if not products:
                return "No products found."
            lines = []
            for p in products:
                status = p.get("status", "N/A")
                variants = len(p.get("variants", []))
                lines.append(f"- {p['title']} (ID: {p['id']}, {status}, {variants} variants)")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_list_orders(status: str = "any", limit: int = 20) -> str:
    """List recent orders from the Shopify store."""
    config = _config()
    access_token = config.get("access_token", "")
    store = config.get("store", "")
    if not access_token or not store:
        return "Error: access_token and store must be configured. Run: steelclaw skills configure shopify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(store)}/orders.json",
                headers=_headers(access_token),
                params={"status": status, "limit": limit},
            )
            resp.raise_for_status()
            orders = resp.json().get("orders", [])
            if not orders:
                return "No orders found."
            lines = []
            for o in orders:
                total = o.get("total_price", "0.00")
                currency = o.get("currency", "USD")
                lines.append(f"- Order #{o.get('order_number', o['id'])}: {total} {currency} ({o.get('financial_status', 'N/A')})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_order(order_id: str) -> str:
    """Get details of a specific Shopify order."""
    config = _config()
    access_token = config.get("access_token", "")
    store = config.get("store", "")
    if not access_token or not store:
        return "Error: access_token and store must be configured. Run: steelclaw skills configure shopify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(store)}/orders/{order_id}.json",
                headers=_headers(access_token),
            )
            resp.raise_for_status()
            order = resp.json().get("order", {})
            customer = order.get("customer", {})
            customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or "N/A"
            return (
                f"Order #{order.get('order_number', order.get('id', 'N/A'))}\n"
                f"Customer: {customer_name}\n"
                f"Total: {order.get('total_price', '0.00')} {order.get('currency', 'USD')}\n"
                f"Financial Status: {order.get('financial_status', 'N/A')}\n"
                f"Fulfillment Status: {order.get('fulfillment_status', 'unfulfilled')}\n"
                f"Items: {len(order.get('line_items', []))}"
            )
    except Exception as e:
        return f"Error: {e}"
