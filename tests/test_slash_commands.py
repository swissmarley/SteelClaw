"""Tests for slash command registration, dispatch, and Discord interaction handling."""

from __future__ import annotations

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


# ── command_handler: basic dispatch ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_returns_text():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/help")
    assert result is not None
    assert "/help" in result
    assert "/status" in result


@pytest.mark.asyncio
async def test_start_is_alias_for_help():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/start")
    assert result is not None
    assert "/help" in result or "Commands" in result


@pytest.mark.asyncio
async def test_status_without_session():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/status")
    assert result is not None
    assert "Online" in result or "Status" in result


@pytest.mark.asyncio
async def test_status_with_session():
    from steelclaw.gateway.command_handler import dispatch_command

    session = MagicMock()
    session.id = "abc123def456"
    session.platform = "telegram"
    session.status = "active"
    session.last_activity_at = None

    result = await dispatch_command("/status", session=session)
    assert result is not None
    assert "telegram" in result
    assert "abc123" in result  # truncated session ID


@pytest.mark.asyncio
async def test_run_falls_through_to_llm():
    """'/run <task>' should return None so the LLM handles it."""
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/run write a poem about Python")
    assert result is None


@pytest.mark.asyncio
async def test_unknown_command_falls_through():
    """Unrecognised commands pass through so the LLM can respond naturally."""
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/unknownxyz")
    assert result is None


@pytest.mark.asyncio
async def test_non_slash_message_falls_through():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("Hello, how are you?")
    assert result is None


@pytest.mark.asyncio
async def test_stop_without_session():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/stop")
    assert result is not None
    assert "session" in result.lower() or "goodbye" in result.lower()


@pytest.mark.asyncio
async def test_stop_closes_session():
    from steelclaw.gateway.command_handler import dispatch_command

    session = MagicMock()
    session.id = "sess-001"
    session.status = "active"
    db = AsyncMock()

    result = await dispatch_command("/stop", session=session, db=db)
    assert result is not None
    assert session.status == "closed"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_status_without_session():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/memory status")
    assert result is not None
    assert "session" in result.lower() or "memory" in result.lower()


@pytest.mark.asyncio
async def test_memory_unknown_action():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/memory invalid_action")
    assert result is not None
    assert "Unknown" in result or "invalid" in result.lower()


@pytest.mark.asyncio
async def test_config_without_settings():
    from steelclaw.gateway.command_handler import dispatch_command

    result = await dispatch_command("/config")
    assert result is not None
    assert "config" in result.lower() or "Configuration" in result


@pytest.mark.asyncio
async def test_new_session_closes_current():
    from steelclaw.gateway.command_handler import dispatch_command

    session = MagicMock()
    session.id = "sess-002"
    session.status = "active"
    db = AsyncMock()

    result = await dispatch_command("/new", session=session, db=db)
    assert result is not None
    assert session.status == "closed"


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

        mock_client.get.assert_called_once()
        get_url = mock_client.get.call_args[0][0]
        assert "/users/@me" in get_url

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

        mock_client.put.assert_not_called()


# ── Discord: interaction-based slash command routing ─────────────────────────


@pytest.mark.asyncio
async def test_discord_send_uses_interaction_followup_when_pending():
    """send() routes reply through interaction.followup when a pending interaction exists."""
    from steelclaw.gateway.connectors.discord import DiscordConnector
    from steelclaw.schemas.messages import OutboundMessage

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = DiscordConnector(config=config, handler=AsyncMock())

    mock_interaction = MagicMock()
    mock_interaction.followup = AsyncMock()
    connector._pending_interactions["interaction-42"] = mock_interaction

    message = OutboundMessage(
        platform="discord",
        platform_chat_id="999",
        content="Hello from command handler",
        reply_to_message_id="interaction-42",
    )

    await connector.send(message)

    mock_interaction.followup.send.assert_awaited_once_with("Hello from command handler")
    # Interaction should be consumed (popped)
    assert "interaction-42" not in connector._pending_interactions


@pytest.mark.asyncio
async def test_discord_send_truncates_long_content():
    """send() truncates content to Discord's 2000-char limit."""
    from steelclaw.gateway.connectors.discord import DiscordConnector, _DISCORD_MAX_LEN
    from steelclaw.schemas.messages import OutboundMessage

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = DiscordConnector(config=config, handler=AsyncMock())

    mock_interaction = MagicMock()
    mock_interaction.followup = AsyncMock()
    connector._pending_interactions["interaction-long"] = mock_interaction

    long_content = "x" * 3000
    message = OutboundMessage(
        platform="discord",
        platform_chat_id="111",
        content=long_content,
        reply_to_message_id="interaction-long",
    )

    await connector.send(message)

    sent_text = mock_interaction.followup.send.call_args[0][0]
    assert len(sent_text) <= _DISCORD_MAX_LEN


@pytest.mark.asyncio
async def test_discord_send_falls_back_to_channel_without_pending_interaction():
    """send() uses the channel when no pending interaction exists."""
    from steelclaw.gateway.connectors.discord import DiscordConnector
    from steelclaw.schemas.messages import OutboundMessage

    config = ConnectorConfig(enabled=True, token="test-token")
    connector = DiscordConnector(config=config, handler=AsyncMock())

    mock_channel = AsyncMock()
    mock_client = MagicMock()
    mock_client.get_channel.return_value = mock_channel
    connector._client = mock_client

    message = OutboundMessage(
        platform="discord",
        platform_chat_id="777",
        content="regular reply",
        reply_to_message_id="some-message-id",  # not in pending_interactions
    )

    await connector.send(message)

    mock_channel.send.assert_awaited_once()


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


# ── Gateway router: slash command interception ───────────────────────────────


@pytest.mark.asyncio
async def test_router_intercepts_help_command():
    """process_message() returns /help response without calling the LLM agent."""
    from steelclaw.gateway import router as gw_router
    from steelclaw.schemas.messages import InboundMessage

    inbound = InboundMessage(
        platform="telegram",
        platform_chat_id="chat-1",
        platform_user_id="user-1",
        platform_message_id="msg-1",
        content="/help",
    )

    # Minimal mock objects
    mock_session = MagicMock()
    mock_session.id = "sess-router-1"
    mock_session.unified_session_id = None
    mock_session.status = "active"

    mock_sm = AsyncMock()
    mock_sm.resolve.return_value = mock_session

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    mock_settings = MagicMock()

    # Patch session manager and agent router
    original_sm = gw_router._session_manager
    original_agent = gw_router._agent_router
    try:
        gw_router._session_manager = mock_sm
        gw_router._agent_router = MagicMock()  # should NOT be called

        outbound = await gw_router.process_message(inbound, mock_settings, mock_db)

        assert outbound is not None
        assert "/help" in outbound.content or "Commands" in outbound.content
        # LLM agent should not have been invoked
        gw_router._agent_router.route_with_usage.assert_not_called()
    finally:
        gw_router._session_manager = original_sm
        gw_router._agent_router = original_agent


@pytest.mark.asyncio
async def test_router_passes_run_command_to_llm():
    """/run falls through to the LLM since dispatch_command returns None."""
    from steelclaw.gateway import router as gw_router
    from steelclaw.schemas.messages import InboundMessage, OutboundMessage

    inbound = InboundMessage(
        platform="telegram",
        platform_chat_id="chat-2",
        platform_user_id="user-2",
        platform_message_id="msg-2",
        content="/run write a haiku",
    )

    mock_session = MagicMock()
    mock_session.id = "sess-router-2"
    mock_session.unified_session_id = None
    mock_session.status = "active"

    mock_sm = AsyncMock()
    mock_sm.resolve.return_value = mock_session

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    mock_settings = MagicMock()

    expected_outbound = OutboundMessage(
        platform="telegram",
        platform_chat_id="chat-2",
        content="Here is your haiku…",
        reply_to_message_id="msg-2",
    )

    mock_agent_result = MagicMock()
    mock_agent_result.outbound = expected_outbound
    mock_agent_result.model = "gpt-4o-mini"
    mock_agent_result.token_usage_prompt = 10
    mock_agent_result.token_usage_completion = 20
    mock_agent_result.cost_usd = 0.001

    mock_agent = AsyncMock()
    mock_agent.route_with_usage.return_value = mock_agent_result

    original_sm = gw_router._session_manager
    original_agent = gw_router._agent_router
    original_ingestor = gw_router._memory_ingestor
    try:
        gw_router._session_manager = mock_sm
        gw_router._agent_router = mock_agent
        gw_router._memory_ingestor = None

        outbound = await gw_router.process_message(inbound, mock_settings, mock_db)

        # LLM agent must have been called
        mock_agent.route_with_usage.assert_awaited_once()
        assert outbound is not None
        assert outbound.content == "Here is your haiku…"
    finally:
        gw_router._session_manager = original_sm
        gw_router._agent_router = original_agent
        gw_router._memory_ingestor = original_ingestor
