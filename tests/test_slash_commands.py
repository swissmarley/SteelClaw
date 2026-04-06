"""Tests for slash command registration and handling across connectors."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from steelclaw.gateway.commands import SLASH_COMMANDS
from steelclaw.settings import ConnectorConfig


# ── Command registry ─────────────────────────────────────────────────────────


def test_slash_commands_not_empty():
    assert len(SLASH_COMMANDS) > 0


def test_slash_commands_have_required_fields():
    for cmd in SLASH_COMMANDS:
        assert "name" in cmd, f"Missing 'name' in {cmd}"
        assert "description" in cmd, f"Missing 'description' in {cmd}"
        assert cmd["name"], "Command name must not be empty"
        assert cmd["description"], "Command description must not be empty"


def test_slash_commands_include_core_commands():
    names = {cmd["name"] for cmd in SLASH_COMMANDS}
    for expected in ("help", "status", "run", "stop", "config", "memory"):
        assert expected in names, f"Expected command /{expected} not found in registry"


def test_slash_commands_names_have_no_slash_prefix():
    for cmd in SLASH_COMMANDS:
        assert not cmd["name"].startswith("/"), (
            f"Command name '{cmd['name']}' must not include a leading slash"
        )


# ── Telegram register_commands ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_register_commands_calls_set_my_commands():
    from steelclaw.gateway.connectors.telegram import TelegramConnector

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = TelegramConnector(config=config, handler=AsyncMock())

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "result": True}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        await connector.register_commands()

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "setMyCommands" in url
        payload = call_args.kwargs.get("json") or call_args[1].get("json", {})
        assert "commands" in payload
        assert len(payload["commands"]) == len(SLASH_COMMANDS)


@pytest.mark.asyncio
async def test_telegram_register_commands_no_token():
    from steelclaw.gateway.connectors.telegram import TelegramConnector

    config = ConnectorConfig(enabled=True, token=None)
    connector = TelegramConnector(config=config, handler=AsyncMock())

    with patch("httpx.AsyncClient") as mock_client_cls:
        await connector.register_commands()
        # Should return early without making any HTTP calls
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_register_commands_api_failure_logs_warning(caplog):
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    import logging

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = TelegramConnector(config=config, handler=AsyncMock())

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with caplog.at_level(logging.WARNING, logger="steelclaw.gateway.telegram"):
            await connector.register_commands()

    assert any("setMyCommands" in r.message for r in caplog.records)


# ── Discord register_commands ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discord_register_commands_calls_application_commands_api():
    from steelclaw.gateway.connectors.discord import DiscordConnector

    config = ConnectorConfig(enabled=True, token="Bot test-token")
    connector = DiscordConnector(config=config, handler=AsyncMock())

    me_response = MagicMock()
    me_response.json.return_value = {"id": "123456789"}
    me_response.raise_for_status = MagicMock()

    put_response = MagicMock()
    put_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value = me_response
        mock_client.put.return_value = put_response

        await connector.register_commands()

        # Should have fetched bot identity
        mock_client.get.assert_called_once()
        get_url = mock_client.get.call_args[0][0]
        assert "/users/@me" in get_url

        # Should have registered commands
        mock_client.put.assert_called_once()
        put_url = mock_client.put.call_args[0][0]
        assert "123456789" in put_url
        assert "/commands" in put_url

        payload = mock_client.put.call_args.kwargs.get("json") or mock_client.put.call_args[1].get("json", [])
        assert len(payload) == len(SLASH_COMMANDS)
        for cmd in payload:
            assert cmd["type"] == 1  # CHAT_INPUT


@pytest.mark.asyncio
async def test_discord_register_commands_no_token():
    from steelclaw.gateway.connectors.discord import DiscordConnector

    config = ConnectorConfig(enabled=True, token=None)
    connector = DiscordConnector(config=config, handler=AsyncMock())

    with patch("httpx.AsyncClient") as mock_client_cls:
        await connector.register_commands()
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_discord_register_commands_missing_application_id_skips(caplog):
    from steelclaw.gateway.connectors.discord import DiscordConnector
    import logging

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = DiscordConnector(config=config, handler=AsyncMock())

    me_response = MagicMock()
    me_response.json.return_value = {}  # no 'id' field
    me_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value = me_response

        with caplog.at_level(logging.WARNING, logger="steelclaw.gateway.discord"):
            await connector.register_commands()

        # put() should NOT be called when application_id is absent
        mock_client.put.assert_not_called()


# ── Slack register_commands ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_register_commands_logs_command_names(caplog):
    from steelclaw.gateway.connectors.slack import SlackConnector
    import logging

    config = ConnectorConfig(enabled=True, token="xoxb-test")
    connector = SlackConnector(config=config, handler=AsyncMock())

    with caplog.at_level(logging.INFO, logger="steelclaw.gateway.slack"):
        await connector.register_commands()

    combined = " ".join(r.message for r in caplog.records)
    for cmd in SLASH_COMMANDS:
        assert f"/{cmd['name']}" in combined, (
            f"/{cmd['name']} not mentioned in Slack register_commands log output"
        )


# ── Slack slash command dispatch ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_handle_slash_command_dispatches_inbound():
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.schemas.messages import InboundMessage

    received: list[InboundMessage] = []

    async def handler(msg: InboundMessage) -> None:
        received.append(msg)

    config = ConnectorConfig(enabled=True, token="xoxb-test")
    connector = SlackConnector(config=config, handler=handler)

    payload = {
        "type": "slash_commands",
        "command": "/help",
        "text": "",
        "channel_id": "C123",
        "user_id": "U456",
        "user_name": "alice",
        "trigger_id": "trigger-789",
    }

    await connector._handle_slash_command(payload)

    assert len(received) == 1
    msg = received[0]
    assert msg.platform == "slack"
    assert msg.content == "/help"
    assert msg.platform_chat_id == "C123"
    assert msg.platform_user_id == "U456"


@pytest.mark.asyncio
async def test_slack_handle_slash_command_includes_args():
    from steelclaw.gateway.connectors.slack import SlackConnector
    from steelclaw.schemas.messages import InboundMessage

    received: list[InboundMessage] = []

    async def handler(msg: InboundMessage) -> None:
        received.append(msg)

    config = ConnectorConfig(enabled=True, token="xoxb-test")
    connector = SlackConnector(config=config, handler=handler)

    payload = {
        "type": "slash_commands",
        "command": "/run",
        "text": "echo hello",
        "channel_id": "C999",
        "user_id": "U111",
        "user_name": "bob",
        "trigger_id": "trigger-000",
    }

    await connector._handle_slash_command(payload)

    assert received[0].content == "/run echo hello"


# ── BaseConnector.start() calls register_commands ────────────────────────────


@pytest.mark.asyncio
async def test_base_connector_start_calls_register_commands():
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.schemas.messages import OutboundMessage

    class DummyConnector(BaseConnector):
        platform_name = "dummy"
        register_commands_called = False

        async def register_commands(self) -> None:
            self.register_commands_called = True

        async def _run(self) -> None:
            pass  # no-op loop

        async def send(self, message: OutboundMessage) -> None:
            pass

    config = ConnectorConfig(enabled=True, token="tok")
    connector = DummyConnector(config=config, handler=AsyncMock())

    await connector.start()
    assert connector.register_commands_called
    await connector.stop()
