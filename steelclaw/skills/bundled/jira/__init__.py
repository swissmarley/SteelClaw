"""Jira Cloud integration — search, create, and retrieve issues."""

from __future__ import annotations

import base64

import httpx

from steelclaw.skills.credential_store import get_all_credentials


def _config() -> dict:
    return get_all_credentials("jira")


def _base_url(domain: str) -> str:
    return f"https://{domain}.atlassian.net/rest/api/3"


def _headers(email: str, api_token: str) -> dict:
    creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def tool_search_issues(jql: str, max_results: int = 20) -> str:
    """Search Jira issues using JQL."""
    config = _config()
    email = config.get("email", "")
    api_token = config.get("api_token", "")
    domain = config.get("domain", "")
    if not all([email, api_token, domain]):
        return "Error: email, api_token, and domain must be configured. Run: steelclaw skills configure jira"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(domain)}/search",
                headers=_headers(email, api_token),
                params={"jql": jql, "maxResults": max_results},
            )
            resp.raise_for_status()
            issues = resp.json().get("issues", [])
            if not issues:
                return "No issues found."
            lines = []
            for i in issues:
                fields = i.get("fields", {})
                status = fields.get("status", {}).get("name", "N/A")
                lines.append(f"- {i['key']}: {fields.get('summary', 'Untitled')} [{status}]")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_issue(project_key: str, summary: str, issue_type: str = "Task", description: str = "") -> str:
    """Create a new Jira issue."""
    config = _config()
    email = config.get("email", "")
    api_token = config.get("api_token", "")
    domain = config.get("domain", "")
    if not all([email, api_token, domain]):
        return "Error: email, api_token, and domain must be configured. Run: steelclaw skills configure jira"
    try:
        payload: dict = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }
        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_base_url(domain)}/issue",
                headers=_headers(email, api_token),
                json=payload,
            )
            resp.raise_for_status()
            issue = resp.json()
            return f"Issue created. Key: {issue['key']}\nURL: https://{domain}.atlassian.net/browse/{issue['key']}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_issue(issue_key: str) -> str:
    """Retrieve a Jira issue by key."""
    config = _config()
    email = config.get("email", "")
    api_token = config.get("api_token", "")
    domain = config.get("domain", "")
    if not all([email, api_token, domain]):
        return "Error: email, api_token, and domain must be configured. Run: steelclaw skills configure jira"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_base_url(domain)}/issue/{issue_key}",
                headers=_headers(email, api_token),
            )
            resp.raise_for_status()
            issue = resp.json()
            fields = issue.get("fields", {})
            status = fields.get("status", {}).get("name", "N/A")
            assignee = fields.get("assignee", {})
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            return (
                f"Issue: {issue['key']}\n"
                f"Summary: {fields.get('summary', 'N/A')}\n"
                f"Status: {status}\n"
                f"Assignee: {assignee_name}\n"
                f"Type: {fields.get('issuetype', {}).get('name', 'N/A')}\n"
                f"Priority: {fields.get('priority', {}).get('name', 'N/A')}"
            )
    except Exception as e:
        return f"Error: {e}"
