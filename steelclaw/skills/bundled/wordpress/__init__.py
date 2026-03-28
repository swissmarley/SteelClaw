"""WordPress REST API integration."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _get_config() -> dict:
    return get_all_credentials("wordpress")


def _get_auth_header(config: dict) -> dict:
    username = config.get("username", "")
    app_password = config.get("app_password", "")
    if not username or not app_password:
        return {}
    token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def tool_create_post(title: str, content: str, status: str = "draft") -> str:
    """Create a new WordPress post."""
    config = _get_config()
    site_url = config.get("site_url")
    if not site_url:
        return "Error: WordPress site_url not configured. Run: steelclaw skills configure wordpress"

    headers = _get_auth_header(config)
    if not headers:
        return "Error: WordPress credentials not configured (username, app_password)."

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{site_url}/wp-json/wp/v2/posts",
                headers=headers,
                json={"title": title, "content": content, "status": status},
            )
            resp.raise_for_status()
            post = resp.json()
            return f"Post created: '{post['title']['rendered']}' (ID: {post['id']}, Status: {post['status']})"
    except Exception as e:
        return f"Error creating post: {e}"


async def tool_list_posts(count: int = 10) -> str:
    """List recent WordPress posts."""
    config = _get_config()
    site_url = config.get("site_url")
    if not site_url:
        return "Error: WordPress site_url not configured."

    headers = _get_auth_header(config)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{site_url}/wp-json/wp/v2/posts",
                headers=headers,
                params={"per_page": count, "orderby": "date", "order": "desc"},
            )
            resp.raise_for_status()
            posts = resp.json()
            if not posts:
                return "No posts found."
            lines = []
            for p in posts:
                lines.append(f"- [{p['status']}] {p['title']['rendered']} (ID: {p['id']}, {p['date'][:10]})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error listing posts: {e}"


async def tool_upload_media(file_path: str) -> str:
    """Upload a media file to WordPress."""
    config = _get_config()
    site_url = config.get("site_url")
    if not site_url:
        return "Error: WordPress site_url not configured."

    headers = _get_auth_header(config)
    if not headers:
        return "Error: WordPress credentials not configured."

    path = Path(file_path).expanduser()
    if not path.exists():
        return f"Error: File not found: {file_path}"

    try:
        content_type = "application/octet-stream"
        if path.suffix.lower() in (".jpg", ".jpeg"):
            content_type = "image/jpeg"
        elif path.suffix.lower() == ".png":
            content_type = "image/png"
        elif path.suffix.lower() == ".gif":
            content_type = "image/gif"

        headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        headers["Content-Type"] = content_type

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{site_url}/wp-json/wp/v2/media",
                headers=headers,
                content=path.read_bytes(),
            )
            resp.raise_for_status()
            media = resp.json()
            return f"Media uploaded: {media.get('source_url', 'unknown')} (ID: {media['id']})"
    except Exception as e:
        return f"Error uploading media: {e}"
