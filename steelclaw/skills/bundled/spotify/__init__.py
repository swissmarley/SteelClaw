"""Spotify Web API integration — search tracks, get playlists, and check now playing."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.spotify.com/v1"


def _config() -> dict:
    return get_all_credentials("spotify")


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def tool_search_tracks(query: str, limit: int = 10) -> str:
    """Search for tracks on Spotify."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure spotify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/search",
                headers=_headers(api_key),
                params={"q": query, "type": "track", "limit": limit},
            )
            resp.raise_for_status()
            tracks = resp.json().get("tracks", {}).get("items", [])
            if not tracks:
                return "No tracks found."
            lines = []
            for t in tracks:
                name = t.get("name", "Untitled")
                artists = ", ".join(a.get("name", "Unknown") for a in t.get("artists", []))
                album = t.get("album", {}).get("name", "N/A")
                url = t.get("external_urls", {}).get("spotify", "")
                lines.append(f"- {name} by {artists} [{album}]\n  {url}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_playlist(playlist_id: str) -> str:
    """Get details and tracks of a Spotify playlist."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure spotify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/playlists/{playlist_id}",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            playlist = resp.json()
            name = playlist.get("name", "Untitled")
            owner = playlist.get("owner", {}).get("display_name", "Unknown")
            total = playlist.get("tracks", {}).get("total", 0)
            tracks = playlist.get("tracks", {}).get("items", [])
            lines = [f"Playlist: {name}", f"Owner: {owner}", f"Total tracks: {total}", ""]
            for item in tracks[:20]:
                track = item.get("track", {})
                track_name = track.get("name", "Untitled")
                artists = ", ".join(a.get("name", "Unknown") for a in track.get("artists", []))
                lines.append(f"- {track_name} by {artists}")
            if total > 20:
                lines.append(f"... and {total - 20} more tracks")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_now_playing() -> str:
    """Get the currently playing track on Spotify."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure spotify"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/me/player/currently-playing",
                headers=_headers(api_key),
            )
            if resp.status_code == 204:
                return "Nothing is currently playing."
            resp.raise_for_status()
            data = resp.json()
            if not data or not data.get("item"):
                return "Nothing is currently playing."
            track = data["item"]
            name = track.get("name", "Untitled")
            artists = ", ".join(a.get("name", "Unknown") for a in track.get("artists", []))
            album = track.get("album", {}).get("name", "N/A")
            progress = data.get("progress_ms", 0) // 1000
            duration = track.get("duration_ms", 0) // 1000
            is_playing = data.get("is_playing", False)
            status = "Playing" if is_playing else "Paused"
            return (
                f"Status: {status}\n"
                f"Track: {name}\n"
                f"Artist: {artists}\n"
                f"Album: {album}\n"
                f"Progress: {progress // 60}:{progress % 60:02d} / {duration // 60}:{duration % 60:02d}"
            )
    except Exception as e:
        return f"Error: {e}"
