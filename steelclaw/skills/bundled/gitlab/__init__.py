"""GitLab integration — list projects, create issues, list pipelines."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://gitlab.com/api/v4"


def _config() -> dict:
    return get_all_credentials("gitlab")


def _headers(api_key: str) -> dict:
    return {"PRIVATE-TOKEN": api_key}


async def tool_list_projects(search: str = "") -> str:
    """List GitLab projects accessible to the authenticated user."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure gitlab"
    try:
        params: dict = {"membership": "true", "per_page": 20}
        if search:
            params["search"] = search
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/projects",
                headers=_headers(api_key),
                params=params,
            )
            resp.raise_for_status()
            projects = resp.json()
            if not projects:
                return "No projects found."
            lines = []
            for p in projects:
                lines.append(f"- {p['path_with_namespace']} (ID: {p['id']}, {p.get('visibility', 'N/A')})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_issue(project_id: str, title: str, description: str = "") -> str:
    """Create a new issue in a GitLab project."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure gitlab"
    try:
        payload: dict = {"title": title}
        if description:
            payload["description"] = description
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/projects/{project_id}/issues",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            issue = resp.json()
            return f"Issue created. #{issue['iid']}: {issue['title']}\nURL: {issue['web_url']}"
    except Exception as e:
        return f"Error: {e}"


async def tool_list_pipelines(project_id: str, status: str = "") -> str:
    """List pipelines for a GitLab project."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure gitlab"
    try:
        params: dict = {"per_page": 20}
        if status:
            params["status"] = status
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/projects/{project_id}/pipelines",
                headers=_headers(api_key),
                params=params,
            )
            resp.raise_for_status()
            pipelines = resp.json()
            if not pipelines:
                return "No pipelines found."
            lines = []
            for p in pipelines:
                lines.append(f"- Pipeline #{p['id']}: {p['status']} (ref: {p.get('ref', 'N/A')}, created: {p.get('created_at', 'N/A')})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
