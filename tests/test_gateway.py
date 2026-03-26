"""Tests for the WebSocket gateway endpoint."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_websocket_echo(app):
    """Connect via WebSocket, send a message, receive a response.

    In Phase 2 the agent tries LLM but falls back to an error message
    when no API key is configured. We verify the pipeline still works.
    """
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/gateway/ws") as ws:
            ws.send_text(json.dumps({"content": "ping"}))
            data = json.loads(ws.receive_text())
            # The agent will return either an echo (no agent set) or an error message
            assert "content" in data
            assert len(data["content"]) > 0


@pytest.mark.asyncio
async def test_webhook_placeholder(client):
    resp = await client.post("/gateway/webhook/slack")
    assert resp.status_code == 200
    assert resp.json()["platform"] == "slack"
