"""Tests for connector live-start/stop via the config API."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from steelclaw.settings import (
    AgentSettings, DatabaseSettings, GatewaySettings,
    LLMSettings, Settings,
)


def _make_settings():
    return Settings(
        database=DatabaseSettings(url="sqlite+aiosqlite://", echo=False),
        gateway=GatewaySettings(dm_allowlist_enabled=False),
        agents=AgentSettings(llm=LLMSettings(api_key="sk-test")),
    )


@pytest.fixture()
async def config_app_client():
    from steelclaw.app import create_app
    app = create_app(_make_settings())
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac


async def test_enable_connector_calls_start(config_app_client):
    """PUT /api/config/connectors/slack with enabled=true calls start_connector."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector.last_error = None
    mock_connector.verify = AsyncMock(return_value=None)
    mock_connector.start = AsyncMock()

    with patch.object(
        app.state.registry, "start_connector", return_value=(mock_connector, None)
    ) as mock_start:
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={
                "enabled": True,
                "token": "xoxb-test",
                "app_token": "xapp-test",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    mock_start.assert_called_once()


async def test_enable_connector_returns_error_on_verify_fail(config_app_client):
    """PUT with enabled=true returns status=error when verify fails."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector.last_error = "auth.test failed: invalid_auth"

    with patch.object(
        app.state.registry,
        "start_connector",
        return_value=(mock_connector, "auth.test failed: invalid_auth"),
    ):
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={"enabled": True, "token": "bad"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "invalid_auth" in data["message"]


async def test_disable_connector_calls_stop(config_app_client):
    """PUT /api/config/connectors/slack with enabled=false calls stop_connector."""
    app, ac = config_app_client

    with patch.object(app.state.registry, "stop_connector", new_callable=AsyncMock) as mock_stop:
        resp = await ac.put(
            "/api/config/connectors/slack",
            json={"enabled": False},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"
    mock_stop.assert_called_once_with("slack")


async def test_connectors_status_includes_last_error(config_app_client):
    """GET /api/config/connectors includes last_error for failed connectors."""
    app, ac = config_app_client

    mock_connector = MagicMock()
    mock_connector._task = MagicMock()
    mock_connector._task.done.return_value = True  # task finished (failed)
    mock_connector.last_error = "auth.test failed: invalid_auth"
    mock_connector.stop = AsyncMock()
    app.state.registry._connectors["slack"] = mock_connector

    # Also add slack to gateway config so it appears in the response
    import json
    from steelclaw.api.config import CONFIG_PATH
    cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    cfg.setdefault("gateway", {}).setdefault("connectors", {})["slack"] = {
        "enabled": True, "token": "xoxb-test"
    }
    CONFIG_PATH.write_text(json.dumps(cfg))

    resp = await ac.get("/api/config/connectors")
    assert resp.status_code == 200
    slack_info = resp.json()["connectors"].get("slack", {})
    assert slack_info.get("last_error") == "auth.test failed: invalid_auth"
