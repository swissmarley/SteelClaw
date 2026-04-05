"""Tests for Telegram voice message transcription (Issue #4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from steelclaw.gateway.connectors.telegram import TelegramConnector
from steelclaw.settings import ConnectorConfig


def _make_connector() -> TelegramConnector:
    config = MagicMock(spec=ConnectorConfig)
    config.token = "test-bot-token"
    handler = AsyncMock()
    return TelegramConnector(config=config, handler=handler)


@pytest.mark.asyncio
async def test_text_message_dispatched():
    """Plain text messages should be dispatched normally."""
    connector = _make_connector()
    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 222, "username": "alice"},
            "text": "Hello agent",
        },
    }
    await connector._handle_update(update)
    connector._handler.assert_awaited_once()
    inbound = connector._handler.call_args[0][0]
    assert inbound.content == "Hello agent"


@pytest.mark.asyncio
async def test_voice_message_skipped_without_transcription():
    """Voice messages without a working transcription return None and are skipped."""
    connector = _make_connector()
    update = {
        "update_id": 2,
        "message": {
            "message_id": 11,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 222, "username": "alice"},
            "voice": {"file_id": "voice_file_123", "duration": 5},
        },
    }
    # Patch _transcribe_voice to simulate failure (e.g. no API key)
    connector._transcribe_voice = AsyncMock(return_value=None)
    await connector._handle_update(update)
    # Should NOT dispatch (no content available)
    connector._handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_message_dispatched_after_transcription():
    """Voice messages should be dispatched with transcribed content."""
    connector = _make_connector()
    update = {
        "update_id": 3,
        "message": {
            "message_id": 12,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 222, "username": "bob"},
            "voice": {"file_id": "voice_file_456", "duration": 3},
        },
    }
    connector._transcribe_voice = AsyncMock(return_value="What is the weather today?")
    await connector._handle_update(update)
    connector._handler.assert_awaited_once()
    inbound = connector._handler.call_args[0][0]
    assert inbound.content == "What is the weather today?"
    assert inbound.platform == "telegram"


@pytest.mark.asyncio
async def test_sticker_dispatched_as_image_attachment():
    """Sticker messages are now handled as image attachments and dispatched."""
    from steelclaw.gateway.attachments import build_attachment_dict

    connector = _make_connector()

    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=b"\x00")

    connector._download_attachment = fake_download

    update = {
        "update_id": 4,
        "message": {
            "message_id": 13,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 222},
            "sticker": {"file_id": "sticker_abc"},
        },
    }
    await connector._handle_update(update)
    connector._handler.assert_awaited_once()
    inbound = connector._handler.call_args[0][0]
    assert inbound.attachments is not None
    assert inbound.attachments[0]["category"] == "image"


@pytest.mark.asyncio
async def test_truly_empty_message_ignored():
    """Messages with no text, voice, or any recognised attachment type are ignored."""
    connector = _make_connector()
    update = {
        "update_id": 5,
        "message": {
            "message_id": 14,
            "chat": {"id": 111, "type": "private"},
            "from": {"id": 222},
            # No text, voice, photo, document, audio, video, animation, or sticker
        },
    }
    await connector._handle_update(update)
    connector._handler.assert_not_awaited()
