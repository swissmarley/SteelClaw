"""LinkedIn skill — profile info and post sharing via LinkedIn API."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.linkedin.com/v2"


def _config() -> dict:
    return get_all_credentials("linkedin")


def _headers() -> dict:
    config = _config()
    token = config.get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def tool_get_profile() -> str:
    """Get the authenticated user's LinkedIn profile."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure linkedin"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/me",
                headers=_headers(),
                params={"projection": "(id,firstName,lastName,headline)"},
            )
            resp.raise_for_status()
            data = resp.json()
        first = data.get("firstName", {}).get("localized", {})
        last = data.get("lastName", {}).get("localized", {})
        first_name = next(iter(first.values()), "") if first else ""
        last_name = next(iter(last.values()), "") if last else ""
        headline = data.get("headline", {}).get("localized", {})
        headline_text = next(iter(headline.values()), "") if headline else ""
        lines = [
            f"**{first_name} {last_name}**\n",
            f"- LinkedIn ID: {data.get('id', '')}",
            f"- Headline: {headline_text}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_share_post(text: str) -> str:
    """Share a text post on LinkedIn."""
    config = _config()
    if not config.get("access_token"):
        return "Error: Access token not configured. Run: steelclaw skills configure linkedin"
    # First get the user's URN
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            me_resp = await client.get(f"{BASE_URL}/me", headers=_headers())
            me_resp.raise_for_status()
            me_data = me_resp.json()
            person_id = me_data.get("id", "")
            author_urn = f"urn:li:person:{person_id}"

            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }
            resp = await client.post(
                f"{BASE_URL}/ugcPosts", headers=_headers(), json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        return f"Post shared on LinkedIn (ID: {data.get('id', '')})"
    except Exception as e:
        return f"Error: {e}"
