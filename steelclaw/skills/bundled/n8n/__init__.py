"""n8n workflow automation integration."""

from __future__ import annotations

import json

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "base_url", "label": "n8n Base URL", "type": "text"},
    {"key": "api_key", "label": "n8n API Key", "type": "password"},
]


def _get_config() -> dict:
    return get_all_credentials("n8n")


async def tool_trigger_webhook(url: str, payload: str = "{}") -> str:
    """Trigger an n8n webhook URL."""
    try:
        data = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return "Error: Invalid JSON payload"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=data)
            return f"Webhook triggered. Status: {resp.status_code}. Response: {resp.text[:500]}"
    except Exception as e:
        return f"Error triggering webhook: {e}"


async def tool_list_workflows() -> str:
    """List all n8n workflows."""
    config = _get_config()
    base_url = config.get("base_url", "http://localhost:5678")
    api_key = config.get("api_key")

    if not api_key:
        return "Error: n8n API key not configured. Run: steelclaw skills configure n8n"

    try:
        headers = {"X-N8N-API-KEY": api_key}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{base_url}/api/v1/workflows", headers=headers)
            resp.raise_for_status()
            workflows = resp.json().get("data", [])
            if not workflows:
                return "No workflows found."
            lines = []
            for wf in workflows:
                status = "active" if wf.get("active") else "inactive"
                lines.append(f"- {wf['name']} (ID: {wf['id']}, {status})")
            return "\n".join(lines)
    except Exception as e:
        return f"Error listing workflows: {e}"


async def tool_execute_workflow(workflow_id: str) -> str:
    """Execute an n8n workflow by ID."""
    config = _get_config()
    base_url = config.get("base_url", "http://localhost:5678")
    api_key = config.get("api_key")

    if not api_key:
        return "Error: n8n API key not configured. Run: steelclaw skills configure n8n"

    try:
        headers = {"X-N8N-API-KEY": api_key}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/api/v1/workflows/{workflow_id}/activate",
                headers=headers,
            )
            return f"Workflow {workflow_id} execution triggered. Status: {resp.status_code}"
    except Exception as e:
        return f"Error executing workflow: {e}"
