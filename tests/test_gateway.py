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


def test_base_connector_last_error_default():
    """BaseConnector starts with last_error=None and is_running=False."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.settings import ConnectorConfig

    class _DummyConnector(BaseConnector):
        platform_name = "dummy"
        async def _run(self): pass
        async def send(self, message): pass

    conn = _DummyConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=AsyncMock(),
    )
    assert conn.last_error is None
    assert conn.is_running is False


@pytest.mark.asyncio
async def test_base_connector_verify_returns_none():
    """Default verify() returns None (no error)."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.settings import ConnectorConfig

    class _DummyConnector(BaseConnector):
        platform_name = "dummy"
        async def _run(self): pass
        async def send(self, message): pass

    conn = _DummyConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=AsyncMock(),
    )
    result = await conn.verify()
    assert result is None


@pytest.mark.asyncio
async def test_registry_start_connector():
    """start_connector starts a connector and adds it to _connectors."""
    from unittest.mock import AsyncMock, patch
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig, GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)
    registry.set_handler(AsyncMock())

    conf = ConnectorConfig(enabled=True, token="tok-test")

    mock_connector = AsyncMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value=None)

    with patch.object(ConnectorRegistry, "_import_connector", return_value=lambda **kw: mock_connector):
        result, error = await registry.start_connector("telegram", conf)

    assert error is None
    assert "telegram" in registry._connectors
    mock_connector.start.assert_called_once()


@pytest.mark.asyncio
async def test_registry_start_connector_verify_failure():
    """start_connector returns error without starting task when verify() fails."""
    from unittest.mock import AsyncMock, patch
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig, GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)
    registry.set_handler(AsyncMock())

    conf = ConnectorConfig(enabled=True, token="bad-tok")

    mock_connector = AsyncMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value="auth.test failed: invalid_auth")

    with patch.object(ConnectorRegistry, "_import_connector", return_value=lambda **kw: mock_connector):
        result, error = await registry.start_connector("telegram", conf)

    assert error == "auth.test failed: invalid_auth"
    assert mock_connector.last_error == "auth.test failed: invalid_auth"
    mock_connector.start.assert_not_called()


@pytest.mark.asyncio
async def test_registry_stop_connector():
    """stop_connector stops and removes a connector from _connectors."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import GatewaySettings

    settings = GatewaySettings()
    registry = ConnectorRegistry(settings)

    mock_connector = AsyncMock()
    registry._connectors["slack"] = mock_connector

    await registry.stop_connector("slack")

    mock_connector.stop.assert_called_once()
    assert "slack" not in registry._connectors


@pytest.mark.asyncio
async def test_slack_verify_missing_token():
    """verify() returns error string when bot token is missing."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token=""),
        handler=AsyncMock(),
    )
    error = await conn.verify()
    assert error is not None
    assert "token" in error.lower()


@pytest.mark.asyncio
async def test_slack_verify_missing_app_token():
    """verify() returns error string when app-level token is missing."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-valid"),
        handler=AsyncMock(),
    )
    error = await conn.verify()
    assert error is not None
    assert "app" in error.lower() or "app_token" in error.lower()


@pytest.mark.asyncio
async def test_slack_verify_auth_test_failure():
    """verify() returns error string when auth.test returns ok=false."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-bad", app_token="xapp-test"),
        handler=AsyncMock(),
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": False, "error": "invalid_auth"}

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp
        error = await conn.verify()

    assert error is not None
    assert "invalid_auth" in error


@pytest.mark.asyncio
async def test_slack_verify_success():
    """verify() returns None when auth.test returns ok=true."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.settings import ConnectorConfig

    conn = SlackConnector(
        config=ConnectorConfig(enabled=True, token="xoxb-valid", app_token="xapp-valid"),
        handler=AsyncMock(),
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ok": True, "user": "testbot", "team": "TestTeam"}

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp
        error = await conn.verify()

    assert error is None
