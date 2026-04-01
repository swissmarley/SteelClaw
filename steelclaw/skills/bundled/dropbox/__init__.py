"""Dropbox skill — manage files via Dropbox API."""

from __future__ import annotations

import json
import httpx
from pathlib import Path

from steelclaw.skills.credential_store import get_all_credentials

API_URL = "https://api.dropboxapi.com/2"
CONTENT_URL = "https://content.dropboxapi.com/2"

required_credentials = [
    {"key": "access_token", "label": "Dropbox Access Token", "type": "password"},
]


def _config() -> dict:
    return get_all_credentials("dropbox")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_list_folder(path: str = "") -> str:
    """List files and folders in a Dropbox path."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure dropbox"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_URL}/files/list_folder",
                headers=_headers(),
                json={"path": path or "", "limit": 100},
            )
            resp.raise_for_status()
            data = resp.json()
        entries = data.get("entries", [])
        if not entries:
            return "No files or folders found."
        lines = ["Dropbox contents:\n"]
        for i, entry in enumerate(entries, 1):
            tag = entry.get(".tag", "file")
            name = entry.get("name", "")
            size = entry.get("size", "")
            size_str = f" ({size} bytes)" if size else ""
            lines.append(f"{i}. [{tag}] **{name}**{size_str}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_upload_file(local_path: str, dropbox_path: str) -> str:
    """Upload a file to Dropbox."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure dropbox"
    p = Path(local_path)
    if not p.exists():
        return f"Error: File not found: {local_path}"
    try:
        token = config.get("access_token", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Dropbox-API-Arg": json.dumps({"path": dropbox_path, "mode": "overwrite"}),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{CONTENT_URL}/files/upload",
                headers=headers,
                content=p.read_bytes(),
            )
            resp.raise_for_status()
            data = resp.json()
        return f"Uploaded: **{data.get('name')}** to {data.get('path_display', dropbox_path)}"
    except Exception as e:
        return f"Error: {e}"


async def tool_download_file(dropbox_path: str, local_path: str) -> str:
    """Download a file from Dropbox."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure dropbox"
    try:
        token = config.get("access_token", "")
        headers = {
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": dropbox_path}),
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{CONTENT_URL}/files/download",
                headers=headers,
            )
            resp.raise_for_status()
            Path(local_path).write_bytes(resp.content)
        return f"Downloaded {dropbox_path} to {local_path}"
    except Exception as e:
        return f"Error: {e}"
