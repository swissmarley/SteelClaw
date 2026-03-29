"""YouTube Data API v3 integration — search videos and get video details."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://www.googleapis.com/youtube/v3"


def _config() -> dict:
    return get_all_credentials("youtube")


async def tool_search_videos(query: str, max_results: int = 5) -> str:
    """Search for YouTube videos by query."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure youtube"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/search",
                params={
                    "key": api_key,
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": max_results,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                return "No videos found."
            lines = []
            for item in items:
                video_id = item.get("id", {}).get("videoId", "N/A")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "Untitled")
                channel = snippet.get("channelTitle", "Unknown")
                lines.append(f"- {title} (by {channel})\n  https://youtube.com/watch?v={video_id}")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_video_details(video_id: str) -> str:
    """Get detailed information about a YouTube video."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure youtube"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/videos",
                params={
                    "key": api_key,
                    "id": video_id,
                    "part": "snippet,statistics,contentDetails",
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                return f"Video {video_id} not found."
            video = items[0]
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            details = video.get("contentDetails", {})
            return (
                f"Title: {snippet.get('title', 'N/A')}\n"
                f"Channel: {snippet.get('channelTitle', 'N/A')}\n"
                f"Published: {snippet.get('publishedAt', 'N/A')}\n"
                f"Duration: {details.get('duration', 'N/A')}\n"
                f"Views: {stats.get('viewCount', 'N/A')}\n"
                f"Likes: {stats.get('likeCount', 'N/A')}\n"
                f"Comments: {stats.get('commentCount', 'N/A')}\n"
                f"URL: https://youtube.com/watch?v={video_id}"
            )
    except Exception as e:
        return f"Error: {e}"
