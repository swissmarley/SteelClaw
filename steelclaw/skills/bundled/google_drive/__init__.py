"""Google Drive skill — manage files via Google Drive API."""

from __future__ import annotations

import httpx
from pathlib import Path

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


def _config() -> dict:
    return get_all_credentials("google_drive")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


async def tool_list_files(query: str = "", max_results: int = 20) -> str:
    """List files in Google Drive."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_drive"
    params: dict = {"pageSize": max_results, "fields": "files(id,name,mimeType,modifiedTime,size)"}
    if query:
        params["q"] = query
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(BASE_URL, headers=_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
        files = data.get("files", [])
        if not files:
            return "No files found."
        lines = ["Google Drive files:\n"]
        for i, f in enumerate(files, 1):
            lines.append(f"{i}. **{f['name']}** — {f.get('mimeType', '')} (ID: {f['id']})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_upload_file(file_path: str, name: str = "", mime_type: str = "") -> str:
    """Upload a file to Google Drive."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_drive"
    p = Path(file_path)
    if not p.exists():
        return f"Error: File not found: {file_path}"
    file_name = name or p.name
    content_type = mime_type or "application/octet-stream"
    try:
        metadata = {"name": file_name}
        headers = _headers()
        headers["Content-Type"] = content_type
        async with httpx.AsyncClient(timeout=60) as client:
            # Simple upload for files < 5MB
            resp = await client.post(
                f"{UPLOAD_URL}?uploadType=media",
                headers=headers,
                content=p.read_bytes(),
            )
            resp.raise_for_status()
            data = resp.json()
        return f"Uploaded: **{data.get('name')}** (ID: {data.get('id')})"
    except Exception as e:
        return f"Error: {e}"


async def tool_download_file(file_id: str, output_path: str) -> str:
    """Download a file from Google Drive by ID."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure google_drive"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{BASE_URL}/{file_id}",
                headers=_headers(),
                params={"alt": "media"},
            )
            resp.raise_for_status()
            Path(output_path).write_bytes(resp.content)
        return f"Downloaded file {file_id} to {output_path}"
    except Exception as e:
        return f"Error: {e}"
