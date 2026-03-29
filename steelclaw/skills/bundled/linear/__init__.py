"""Linear integration — list, create, and retrieve issues via GraphQL."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "Linear API Key", "type": "password", "test_url": "https://api.linear.app/graphql"},
]

GRAPHQL_URL = "https://api.linear.app/graphql"


def _config() -> dict:
    return get_all_credentials("linear")


def _headers(api_key: str) -> dict:
    return {"Authorization": api_key, "Content-Type": "application/json"}


async def _graphql(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GRAPHQL_URL, headers=_headers(api_key), json=payload)
        resp.raise_for_status()
        return resp.json()


async def tool_list_issues(first: int = 20) -> str:
    """List recent issues from Linear."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure linear"
    try:
        query = """
        query($first: Int!) {
            issues(first: $first, orderBy: updatedAt) {
                nodes { identifier title state { name } assignee { name } }
            }
        }"""
        result = await _graphql(api_key, query, {"first": first})
        issues = result.get("data", {}).get("issues", {}).get("nodes", [])
        if not issues:
            return "No issues found."
        lines = []
        for i in issues:
            state = i.get("state", {}).get("name", "N/A")
            assignee = i.get("assignee", {})
            assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
            lines.append(f"- {i['identifier']}: {i['title']} [{state}] ({assignee_name})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def tool_create_issue(team_id: str, title: str, description: str = "") -> str:
    """Create a new issue in Linear."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure linear"
    try:
        query = """
        mutation($teamId: String!, $title: String!, $description: String) {
            issueCreate(input: { teamId: $teamId, title: $title, description: $description }) {
                success
                issue { identifier title url }
            }
        }"""
        variables: dict = {"teamId": team_id, "title": title}
        if description:
            variables["description"] = description
        result = await _graphql(api_key, query, variables)
        issue_data = result.get("data", {}).get("issueCreate", {})
        if issue_data.get("success"):
            issue = issue_data.get("issue", {})
            return f"Issue created. {issue.get('identifier', 'N/A')}: {issue.get('title', 'N/A')}\nURL: {issue.get('url', 'N/A')}"
        return f"Failed to create issue: {result}"
    except Exception as e:
        return f"Error: {e}"


async def tool_get_issue(issue_id: str) -> str:
    """Get a Linear issue by identifier."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure linear"
    try:
        query = """
        query($id: String!) {
            issue(id: $id) {
                identifier title description state { name }
                assignee { name } priority url createdAt
            }
        }"""
        result = await _graphql(api_key, query, {"id": issue_id})
        issue = result.get("data", {}).get("issue")
        if not issue:
            return f"Issue '{issue_id}' not found."
        state = issue.get("state", {}).get("name", "N/A")
        assignee = issue.get("assignee", {})
        assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
        return (
            f"Issue: {issue['identifier']}\n"
            f"Title: {issue['title']}\n"
            f"Status: {state}\n"
            f"Assignee: {assignee_name}\n"
            f"Priority: {issue.get('priority', 'N/A')}\n"
            f"URL: {issue.get('url', 'N/A')}"
        )
    except Exception as e:
        return f"Error: {e}"
