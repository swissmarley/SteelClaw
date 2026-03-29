"""Twitter/X skill — post tweets, search, and get users via Twitter API v2."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.twitter.com/2"


def _config() -> dict:
    return get_all_credentials("twitter_x")


def _headers() -> dict:
    config = _config()
    token = config.get("bearer_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_post_tweet(text: str) -> str:
    """Post a new tweet."""
    config = _config()
    if not config.get("bearer_token"):
        return "Error: Bearer token not configured. Run: steelclaw skills configure twitter_x"
    if len(text) > 280:
        return f"Error: Tweet too long ({len(text)} chars). Max is 280."
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/tweets",
                headers=_headers(),
                json={"text": text},
            )
            resp.raise_for_status()
            data = resp.json()
        tweet = data.get("data", {})
        return f"Tweet posted (ID: {tweet.get('id', '')}): {tweet.get('text', '')}"
    except Exception as e:
        return f"Error: {e}"


async def tool_search_tweets(query: str, max_results: int = 10) -> str:
    """Search recent tweets."""
    config = _config()
    if not config.get("bearer_token"):
        return "Error: Bearer token not configured. Run: steelclaw skills configure twitter_x"
    max_results = max(10, min(100, max_results))
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/tweets/search/recent",
                headers=_headers(),
                params={
                    "query": query,
                    "max_results": max_results,
                    "tweet.fields": "created_at,author_id,public_metrics",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        tweets = data.get("data", [])
        if not tweets:
            return f"No tweets found for: {query}"
        lines = [f"Recent tweets for: {query}\n"]
        for i, t in enumerate(tweets, 1):
            metrics = t.get("public_metrics", {})
            lines.append(f"{i}. {t.get('text', '')}")
            lines.append(
                f"   Likes: {metrics.get('like_count', 0)} | "
                f"Retweets: {metrics.get('retweet_count', 0)} | "
                f"Created: {t.get('created_at', '')}"
            )
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_get_user(username: str) -> str:
    """Get a Twitter user profile by username."""
    config = _config()
    if not config.get("bearer_token"):
        return "Error: Bearer token not configured. Run: steelclaw skills configure twitter_x"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/users/by/username/{username}",
                headers=_headers(),
                params={"user.fields": "description,public_metrics,created_at,verified"},
            )
            resp.raise_for_status()
            data = resp.json()
        user = data.get("data", {})
        if not user:
            return f"User @{username} not found."
        metrics = user.get("public_metrics", {})
        lines = [
            f"**@{user.get('username', '')}** ({user.get('name', '')})\n",
            f"- Bio: {user.get('description', '')}",
            f"- Followers: {metrics.get('followers_count', 0)}",
            f"- Following: {metrics.get('following_count', 0)}",
            f"- Tweets: {metrics.get('tweet_count', 0)}",
            f"- Joined: {user.get('created_at', '')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
