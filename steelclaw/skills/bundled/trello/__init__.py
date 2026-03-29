"""Trello integration — list boards, list cards, and create cards."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.trello.com/1"


def _config() -> dict:
    return get_all_credentials("trello")


def _auth_params(config: dict) -> dict:
    return {"key": config.get("api_key", ""), "token": config.get("token", "")}


async def tool_list_boards() -> str:
    """List all boards for the authenticated Trello user."""
    config = _config()
    auth = _auth_params(config)
    if not auth["key"] or not auth["token"]:
        return "Error: api_key and token must be configured. Run: steelclaw skills configure trello"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/members/me/boards",
                params={**auth, "fields": "name,url,closed"},
            )
            resp.raise_for_status()
            boards = resp.json()
            if not boards:
                return "No boards found."
            lines = []
            for b in boards:
                if b.get("closed"):
                    continue
                lines.append(f"- {b['id']}: {b.get('name', 'Untitled')}\n  {b.get('url', '')}")
            return "\n".join(lines) if lines else "No open boards found."
    except Exception as e:
        return f"Error: {e}"


async def tool_list_cards(board_id: str) -> str:
    """List all cards on a Trello board."""
    config = _config()
    auth = _auth_params(config)
    if not auth["key"] or not auth["token"]:
        return "Error: api_key and token must be configured. Run: steelclaw skills configure trello"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/boards/{board_id}/cards",
                params={**auth, "fields": "name,idList,url,due,labels"},
            )
            resp.raise_for_status()
            cards = resp.json()
            if not cards:
                return "No cards found on this board."
            lines = []
            for c in cards:
                name = c.get("name", "Untitled")
                due = c.get("due", "No due date")
                labels = ", ".join(lb.get("name", lb.get("color", "")) for lb in c.get("labels", []))
                label_str = f" [{labels}]" if labels else ""
                lines.append(f"- {c['id']}: {name}{label_str} (Due: {due})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_card(list_id: str, name: str, desc: str = "", due: str = "") -> str:
    """Create a new card on a Trello list."""
    config = _config()
    auth = _auth_params(config)
    if not auth["key"] or not auth["token"]:
        return "Error: api_key and token must be configured. Run: steelclaw skills configure trello"
    try:
        payload: dict = {**auth, "idList": list_id, "name": name}
        if desc:
            payload["desc"] = desc
        if due:
            payload["due"] = due
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/cards",
                params=payload,
            )
            resp.raise_for_status()
            card = resp.json()
            return f"Card created. ID: {card['id']}, Name: {name}\nURL: {card.get('url', '')}"
    except Exception as e:
        return f"Error: {e}"
