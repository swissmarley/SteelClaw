"""GitHub integration — list repos, create and list issues."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_token", "label": "GitHub Personal Access Token", "type": "password", "test_url": "https://api.github.com/user"},
]

BASE_URL = "https://api.github.com"


def _config() -> dict:
    return get_all_credentials("github_skill")


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def tool_list_repos(sort: str = "updated") -> str:
    """List repositories for the authenticated GitHub user."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure github_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/user/repos",
                headers=_headers(api_key),
                params={"sort": sort, "per_page": 20},
            )
            resp.raise_for_status()
            repos = resp.json()
            if not repos:
                return "No repositories found."
            lines = []
            for r in repos:
                stars = r.get("stargazers_count", 0)
                lines.append(f"- {r['full_name']} ({'private' if r.get('private') else 'public'}, {stars} stars)")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_issue(owner: str, repo: str, title: str, body: str = "") -> str:
    """Create a new issue in a GitHub repository."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure github_skill"
    try:
        payload: dict = {"title": title}
        if body:
            payload["body"] = body
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/repos/{owner}/{repo}/issues",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            issue = resp.json()
            return f"Issue created. #{issue['number']}: {issue['title']}\nURL: {issue['html_url']}"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_issues(owner: str, repo: str, state: str = "open") -> str:
    """List issues for a GitHub repository."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure github_skill"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/repos/{owner}/{repo}/issues",
                headers=_headers(api_key),
                params={"state": state, "per_page": 20},
            )
            resp.raise_for_status()
            issues = resp.json()
            if not issues:
                return f"No {state} issues found."
            lines = []
            for i in issues:
                labels = ", ".join(l["name"] for l in i.get("labels", []))
                label_str = f" [{labels}]" if labels else ""
                lines.append(f"- #{i['number']}: {i['title']}{label_str} ({i['state']})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
