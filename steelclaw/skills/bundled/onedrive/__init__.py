"""OneDrive skill — manage files via Microsoft Graph API."""

from __future__ import annotations

import httpx
from pathlib import Path

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://graph.microsoft.com/v1.0/me/drive"


def _config() -> dict:
    return get_all_credentials("onedrive")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_list_files(folder_path: str = "") -> str:
    """List files in OneDrive root or a specific folder."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure onedrive"
    if folder_path:
        url = f"{BASE_URL}/root:/{folder_path}:/children"
    else:
        url = f"{BASE_URL}/root/children"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
        items = data.get("value", [])
        if not items:
            return "No files found."
        lines = ["OneDrive files:\n"]
        for i, item in enumerate(items, 1):
            name = item.get("name", "")
            size = item.get("size", 0)
            is_folder = "folder" in item
            tag = "folder" if is_folder else "file"
            lines.append(f"{i}. [{tag}] **{name}** ({size} bytes)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_upload_file(local_path: str, remote_path: str) -> str:
    """Upload a file to OneDrive."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure onedrive"
    p = Path(local_path)
    if not p.exists():
        return f"Error: File not found: {local_path}"
    try:
        token = config.get("access_token", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
        }
        url = f"{BASE_URL}/root:/{remote_path}:/content"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.put(url, headers=headers, content=p.read_bytes())
            resp.raise_for_status()
            data = resp.json()
        return f"Uploaded: **{data.get('name')}** to OneDrive ({data.get('size', 0)} bytes)"
    except Exception as e:
        return f"Error: {e}"
