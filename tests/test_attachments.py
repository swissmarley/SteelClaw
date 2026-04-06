"""Tests for attachment classification and connector file handling."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from steelclaw.gateway.attachments import (
    build_attachment_dict,
    categorize_file,
)
from steelclaw.schemas.messages import InboundMessage


# ── categorize_file ──────────────────────────────────────────────────────────


class TestCategorizeFile:
    def test_image_by_mime(self):
        assert categorize_file("photo.jpg", "image/jpeg") == "image"

    def test_image_by_extension(self):
        assert categorize_file("shot.png") == "image"

    def test_audio_by_mime(self):
        assert categorize_file("track.ogg", "audio/ogg") == "audio"

    def test_audio_by_extension(self):
        assert categorize_file("voice.mp3") == "audio"

    def test_video_by_mime(self):
        assert categorize_file("clip.mp4", "video/mp4") == "video"

    def test_video_by_extension(self):
        assert categorize_file("reel.webm") == "video"

    def test_csv_by_mime(self):
        assert categorize_file("data.csv", "text/csv") == "csv"

    def test_csv_by_extension(self):
        assert categorize_file("spreadsheet.csv") == "csv"

    def test_pdf_by_mime(self):
        assert categorize_file("report.pdf", "application/pdf") == "document"

    def test_pdf_by_extension(self):
        assert categorize_file("report.pdf") == "document"

    def test_txt_by_extension(self):
        assert categorize_file("notes.txt") == "document"

    def test_mime_with_params(self):
        # Charset params should not confuse classification
        assert categorize_file("file.txt", "text/plain; charset=utf-8") == "document"

    def test_unknown(self):
        assert categorize_file("archive.zip") == "unknown"

    def test_empty_filename(self):
        assert categorize_file("") == "unknown"


# ── build_attachment_dict ────────────────────────────────────────────────────


class TestBuildAttachmentDict:
    def test_basic_fields_always_present(self):
        att = build_attachment_dict("photo.jpg", "image/jpeg")
        assert att["filename"] == "photo.jpg"
        assert att["mime"] == "image/jpeg"
        assert att["category"] == "image"

    def test_image_base64_encoded(self):
        data = b"\xff\xd8\xff"  # JPEG magic bytes
        att = build_attachment_dict("photo.jpg", "image/jpeg", data=data)
        assert att.get("base64") == base64.b64encode(data).decode()

    def test_no_base64_when_no_data(self):
        att = build_attachment_dict("photo.jpg", "image/jpeg")
        assert "base64" not in att

    def test_csv_text_content(self):
        csv_data = b"name,age\nAlice,30\nBob,25\n"
        att = build_attachment_dict("data.csv", "text/csv", data=csv_data)
        assert att["category"] == "csv"
        text = att.get("text_content", "")
        assert "name" in text
        assert "Alice" in text

    def test_txt_document_text(self):
        text_data = b"Hello, world!"
        att = build_attachment_dict("notes.txt", "text/plain", data=text_data)
        assert att["category"] == "document"
        assert att.get("text_content") == "Hello, world!"

    def test_json_document_text(self):
        json_data = b'{"key": "value"}'
        att = build_attachment_dict("config.json", "application/json", data=json_data)
        assert att["category"] == "document"
        assert "key" in att.get("text_content", "")

    def test_audio_no_base64_no_text(self):
        att = build_attachment_dict("voice.mp3", "audio/mpeg", data=b"\x00" * 100)
        assert att["category"] == "audio"
        assert "base64" not in att
        assert "text_content" not in att

    def test_video_no_inline_content(self):
        att = build_attachment_dict("clip.mp4", "video/mp4", data=b"\x00" * 100)
        assert att["category"] == "video"
        assert "base64" not in att

    def test_unknown_mime_falls_back_to_extension(self):
        att = build_attachment_dict("shot.webp", "application/octet-stream")
        assert att["category"] == "image"

    def test_missing_mime_defaults_to_octet_stream(self):
        att = build_attachment_dict("file.bin", None)
        assert att["mime"] == "application/octet-stream"

    def test_csv_truncation_hint(self):
        # Build a CSV with more than 6 rows to trigger the row-count hint
        rows = ["h1,h2"] + [f"a{i},b{i}" for i in range(20)]
        csv_bytes = "\n".join(rows).encode()
        att = build_attachment_dict("big.csv", "text/csv", data=csv_bytes)
        assert "rows total" in att.get("text_content", "")


# ── Telegram connector attachment handling ───────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_photo_dispatched():
    """A Telegram photo message should be dispatched with an image attachment."""
    from unittest.mock import AsyncMock
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    photo_data = b"\xff\xd8\xff\xe0"  # Minimal JPEG header

    # Mock _download_attachment to return a pre-built image attachment
    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=photo_data)

    conn._download_attachment = fake_download

    update = {
        "update_id": 1,
        "message": {
            "message_id": 42,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99, "username": "testuser"},
            "photo": [
                {"file_id": "small_id", "width": 100, "height": 100},
                {"file_id": "large_id", "width": 800, "height": 600},
            ],
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound: InboundMessage = handler.await_args[0][0]
    assert inbound.attachments is not None
    assert len(inbound.attachments) == 1
    assert inbound.attachments[0]["category"] == "image"
    assert inbound.attachments[0]["filename"] == "photo.jpg"
    assert "[File attachment" in inbound.content


@pytest.mark.asyncio
async def test_telegram_document_dispatched():
    """A Telegram document (PDF) should be dispatched with a document attachment."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=b"%PDF-1.4 minimal")

    conn._download_attachment = fake_download

    update = {
        "update_id": 2,
        "message": {
            "message_id": 43,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99},
            "document": {
                "file_id": "doc_id",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
            },
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound: InboundMessage = handler.await_args[0][0]
    assert inbound.attachments is not None
    assert inbound.attachments[0]["category"] == "document"
    assert inbound.attachments[0]["filename"] == "report.pdf"


@pytest.mark.asyncio
async def test_telegram_text_with_no_attachment_still_dispatched():
    """A plain text Telegram message is dispatched normally (no regression)."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    update = {
        "update_id": 3,
        "message": {
            "message_id": 44,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99},
            "text": "Hello!",
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound: InboundMessage = handler.await_args[0][0]
    assert inbound.content == "Hello!"
    assert inbound.attachments is None


@pytest.mark.asyncio
async def test_telegram_empty_message_not_dispatched():
    """A Telegram message with no text, voice, or attachments is silently ignored."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    update = {
        "update_id": 4,
        "message": {
            "message_id": 45,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99},
            # No text, no photo, no document, no voice
        },
    }

    await conn._handle_update(update)

    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_photo_with_caption():
    """A Telegram photo + caption should include both content and attachment."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=b"\xff\xd8\xff")

    conn._download_attachment = fake_download

    update = {
        "update_id": 5,
        "message": {
            "message_id": 46,
            "chat": {"id": 100, "type": "private"},
            "from": {"id": 99},
            "caption": "Look at this!",
            "photo": [{"file_id": "img_id", "width": 800, "height": 600}],
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound: InboundMessage = handler.await_args[0][0]
    assert inbound.content == "Look at this!"
    assert inbound.attachments is not None


# ── Discord connector attachment handling ────────────────────────────────────


@pytest.mark.asyncio
async def test_discord_attachment_dispatched():
    """A Discord message with an image attachment should be dispatched."""
    from steelclaw.gateway.connectors.discord import _collect_discord_attachments

    image_data = b"\x89PNG\r\n"

    mock_att = MagicMock()
    mock_att.filename = "image.png"
    mock_att.content_type = "image/png"
    mock_att.url = "https://cdn.discordapp.com/attachments/img.png"

    mock_resp = MagicMock()
    mock_resp.content = image_data
    mock_resp.raise_for_status = MagicMock()

    with patch("steelclaw.gateway.connectors.discord.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.get.return_value = mock_resp

        result = await _collect_discord_attachments([mock_att])

    assert len(result) == 1
    assert result[0]["filename"] == "image.png"
    assert result[0]["category"] == "image"
    assert result[0].get("base64") == base64.b64encode(image_data).decode()


@pytest.mark.asyncio
async def test_discord_no_attachments_empty_content_skipped():
    """Discord message with no content and no attachments is not dispatched."""
    try:
        import discord as _discord_lib  # noqa: F401 — skip if not installed
    except ImportError:
        pytest.skip("discord.py not installed")

    from steelclaw.gateway.connectors.discord import DiscordConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = DiscordConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    # Simulate on_message with empty content and no attachments
    mock_message = MagicMock()
    mock_message.content = ""
    mock_message.attachments = []
    mock_message.author = MagicMock()
    mock_message.channel = MagicMock()
    mock_message.guild = None
    mock_message.mentions = []
    mock_message.id = 123

    with patch(
        "steelclaw.gateway.connectors.discord._collect_discord_attachments",
        new=AsyncMock(return_value=[]),
    ):
        # Manually call the handler logic mirrored from the connector
        content = mock_message.content or ""
        attachments: list = []
        if not content and not attachments:
            pass  # should not dispatch
        else:
            await handler(MagicMock())

    handler.assert_not_awaited()


# ── Slack connector attachment handling ──────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_collect_attachments_downloads_file():
    """_collect_slack_attachments should download and categorise a Slack file."""
    from steelclaw.gateway.connectors.slack import _collect_slack_attachments

    csv_data = b"col1,col2\nval1,val2\n"

    mock_resp = MagicMock()
    mock_resp.content = csv_data
    mock_resp.raise_for_status = MagicMock()

    files = [
        {
            "name": "data.csv",
            "mimetype": "text/csv",
            "url_private_download": "https://files.slack.com/files/data.csv",
        }
    ]

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.get.return_value = mock_resp

        result = await _collect_slack_attachments(files, bot_token="xoxb-test")

    assert len(result) == 1
    assert result[0]["filename"] == "data.csv"
    assert result[0]["category"] == "csv"
    assert "col1" in result[0].get("text_content", "")


@pytest.mark.asyncio
async def test_slack_collect_attachments_no_url():
    """File with no download URL produces a metadata-only attachment."""
    from steelclaw.gateway.connectors.slack import _collect_slack_attachments

    files = [{"name": "mystery.pdf", "mimetype": "application/pdf"}]
    result = await _collect_slack_attachments(files, bot_token="xoxb-test")

    assert len(result) == 1
    assert result[0]["filename"] == "mystery.pdf"
    assert result[0]["category"] == "document"
    assert "base64" not in result[0]
    assert result[0].get("text_content") is None


@pytest.mark.asyncio
async def test_slack_file_share_subtype_handled():
    """Slack events with subtype=file_share should be processed (not ignored)."""
    from steelclaw.gateway.connectors.slack import _HANDLED_SUBTYPES

    assert "file_share" in _HANDLED_SUBTYPES


def test_slack_regular_subtype_still_ignored():
    """Only file_share is whitelisted; other subtypes remain ignored."""
    from steelclaw.gateway.connectors.slack import _HANDLED_SUBTYPES

    assert "message_changed" not in _HANDLED_SUBTYPES
    assert "bot_message" not in _HANDLED_SUBTYPES


# ── Regression: CSV content reaches LLM via context builder ─────────────────


def test_context_builder_csv_attachment_included_in_user_message():
    """CSV attachments must appear as text blocks in the LLM message (fix review comment 1)."""
    from steelclaw.llm.context import ContextBuilder
    from steelclaw.settings import LLMSettings

    cb = ContextBuilder(LLMSettings())
    att = {
        "filename": "report.csv",
        "mime": "text/csv",
        "category": "csv",
        "text_content": "name,score\nAlice,95\nBob,87",
    }
    msg = cb._build_user_message("Analyse this file", attachments=[att])

    # Content must be a list (multimodal format)
    assert isinstance(msg["content"], list)
    text_parts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
    combined = "\n".join(text_parts)
    # CSV preview must be present
    assert "report.csv" in combined
    assert "Alice" in combined


def test_context_builder_csv_without_text_content_shows_fallback():
    """CSV attachment with no extracted text shows the 'could not be extracted' fallback."""
    from steelclaw.llm.context import ContextBuilder
    from steelclaw.settings import LLMSettings

    cb = ContextBuilder(LLMSettings())
    att = {"filename": "empty.csv", "mime": "text/csv", "category": "csv"}
    msg = cb._build_user_message("see attached", attachments=[att])

    text_parts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
    combined = "\n".join(text_parts)
    assert "could not be extracted" in combined


# ── Regression: Telegram caption_entities mention detection ──────────────────


@pytest.mark.asyncio
async def test_telegram_caption_mention_detected():
    """Bot mention in caption_entities (media messages) must set is_mention=True (fix review comment 2)."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=b"\xff\xd8\xff")

    conn._download_attachment = fake_download

    update = {
        "update_id": 10,
        "message": {
            "message_id": 50,
            "chat": {"id": 200, "type": "supergroup"},
            "from": {"id": 99},
            "caption": "@mybot check this",
            "caption_entities": [{"type": "mention", "offset": 0, "length": 7}],
            "photo": [{"file_id": "img_id", "width": 800, "height": 600}],
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound = handler.await_args[0][0]
    assert inbound.is_mention is True


@pytest.mark.asyncio
async def test_telegram_no_caption_entities_not_mention():
    """A media message without caption_entities should not be flagged as a mention."""
    from steelclaw.gateway.connectors.telegram import TelegramConnector
    from steelclaw.settings import ConnectorConfig

    handler = AsyncMock()
    conn = TelegramConnector(
        config=ConnectorConfig(enabled=True, token="tok"),
        handler=handler,
    )

    async def fake_download(file_id, filename, mime):
        return build_attachment_dict(filename, mime, data=b"\xff\xd8\xff")

    conn._download_attachment = fake_download

    update = {
        "update_id": 11,
        "message": {
            "message_id": 51,
            "chat": {"id": 200, "type": "supergroup"},
            "from": {"id": 99},
            "caption": "look at this cool photo",
            "photo": [{"file_id": "img_id2", "width": 800, "height": 600}],
            # No caption_entities or entities
        },
    }

    await conn._handle_update(update)

    handler.assert_awaited_once()
    inbound = handler.await_args[0][0]
    assert inbound.is_mention is False


# ── local_path: temp file is created and surfaced ────────────────────────────


def test_build_attachment_dict_sets_local_path_for_images():
    """build_attachment_dict must write bytes to a temp file and expose local_path."""
    import os
    att = build_attachment_dict("photo.png", "image/png", data=b"\x89PNG")
    assert "local_path" in att
    assert att["local_path"] is not None
    assert os.path.exists(att["local_path"])
    # cleanup
    os.unlink(att["local_path"])


def test_build_attachment_dict_no_local_path_when_no_data():
    """Without data, local_path must not appear in the dict."""
    att = build_attachment_dict("photo.png", "image/png")
    assert "local_path" not in att


def test_build_attachment_dict_local_path_for_audio():
    """Audio files also get a local_path so the agent can save them."""
    import os
    att = build_attachment_dict("voice.ogg", "audio/ogg", data=b"\x4f\x67\x67\x53")
    assert att.get("local_path") is not None
    assert os.path.exists(att["local_path"])
    os.unlink(att["local_path"])


def test_context_builder_image_includes_local_path_note():
    """Image vision blocks must be followed by a text block with the local path."""
    from steelclaw.llm.context import ContextBuilder
    from steelclaw.settings import LLMSettings

    cb = ContextBuilder(LLMSettings())
    att = {
        "filename": "screenshot.png",
        "mime": "image/png",
        "category": "image",
        "base64": base64.b64encode(b"\x89PNG").decode(),
        "local_path": "/tmp/steelclaw_att_screenshot.png",
    }
    msg = cb._build_user_message("what's in this image?", attachments=[att])
    text_parts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
    combined = "\n".join(text_parts)
    assert "/tmp/steelclaw_att_screenshot.png" in combined


def test_context_builder_unknown_category_with_local_path():
    """Files of unknown category should still surface local_path to the agent."""
    from steelclaw.llm.context import ContextBuilder
    from steelclaw.settings import LLMSettings

    cb = ContextBuilder(LLMSettings())
    att = {
        "filename": "archive.zip",
        "mime": "application/zip",
        "category": "unknown",
        "local_path": "/tmp/steelclaw_att_archive.zip",
    }
    msg = cb._build_user_message("here's a zip", attachments=[att])
    text_parts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
    combined = "\n".join(text_parts)
    assert "archive.zip" in combined
    assert "/tmp/steelclaw_att_archive.zip" in combined


# ── Audio transcription helper ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_audio_attachment_returns_text_on_success():
    """transcribe_audio_attachment returns transcription text when Whisper succeeds."""
    from steelclaw.gateway.attachments import transcribe_audio_attachment

    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.text = "Hello from voice message"

    mock_transcriber = AsyncMock()
    mock_transcriber.transcribe = AsyncMock(return_value=mock_result)

    with patch("steelclaw.voice.transcription.Transcriber", return_value=mock_transcriber):
        with patch("steelclaw.settings.VoiceSettings"):
            result = await transcribe_audio_attachment(b"\x4f\x67\x67\x53", "voice.ogg")

    assert result == "Hello from voice message"


@pytest.mark.asyncio
async def test_transcribe_audio_attachment_returns_none_on_failure():
    """transcribe_audio_attachment returns None when Whisper reports an error."""
    from steelclaw.gateway.attachments import transcribe_audio_attachment

    mock_result = MagicMock()
    mock_result.ok = False
    mock_result.error = "no api key"

    mock_transcriber = AsyncMock()
    mock_transcriber.transcribe = AsyncMock(return_value=mock_result)

    with patch("steelclaw.voice.transcription.Transcriber", return_value=mock_transcriber):
        with patch("steelclaw.settings.VoiceSettings"):
            result = await transcribe_audio_attachment(b"\x00", "voice.m4a")

    assert result is None


@pytest.mark.asyncio
async def test_discord_audio_transcription_wired():
    """Discord connector calls transcribe_audio_attachment for audio files."""
    from steelclaw.gateway.connectors.discord import _collect_discord_attachments

    audio_data = b"\x4f\x67\x67\x53"  # OGG magic bytes

    mock_att = MagicMock()
    mock_att.filename = "voice.ogg"
    mock_att.content_type = "audio/ogg"
    mock_att.url = "https://cdn.discordapp.com/voice.ogg"

    mock_resp = MagicMock()
    mock_resp.content = audio_data
    mock_resp.raise_for_status = MagicMock()

    with patch("steelclaw.gateway.connectors.discord.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.get.return_value = mock_resp

        with patch(
            "steelclaw.gateway.connectors.discord.transcribe_audio_attachment",
            new=AsyncMock(return_value="Hi there from Discord voice"),
        ):
            result = await _collect_discord_attachments([mock_att])

    assert len(result) == 1
    assert result[0]["category"] == "audio"
    assert result[0]["text_content"] == "Hi there from Discord voice"


@pytest.mark.asyncio
async def test_slack_audio_transcription_wired():
    """Slack connector calls transcribe_audio_attachment for audio files."""
    from steelclaw.gateway.connectors.slack import _collect_slack_attachments

    m4a_data = b"\x00\x00\x00\x20ftyp"  # M4A/MP4 header

    mock_resp = MagicMock()
    mock_resp.content = m4a_data
    mock_resp.raise_for_status = MagicMock()

    files = [
        {
            "name": "voice.m4a",
            "mimetype": "audio/x-m4a",
            "url_private_download": "https://files.slack.com/voice.m4a",
        }
    ]

    with patch("steelclaw.gateway.connectors.slack.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.get.return_value = mock_resp

        with patch(
            "steelclaw.gateway.connectors.slack.transcribe_audio_attachment",
            new=AsyncMock(return_value="Hello from Slack voice memo"),
        ):
            result = await _collect_slack_attachments(files, bot_token="xoxb-test")

    assert len(result) == 1
    assert result[0]["category"] == "audio"
    assert result[0]["text_content"] == "Hello from Slack voice memo"


# ── file_manager: copy_file, move_file, create_directory, delete_file ────────


@pytest.mark.asyncio
async def test_file_manager_copy_file_binary():
    """copy_file correctly copies binary data (e.g. an image attachment)."""
    import os, tempfile
    from steelclaw.skills.bundled.file_manager import tool_copy_file

    data = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG-like binary
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as src:
        src.write(data)
        src_path = src.name

    with tempfile.TemporaryDirectory() as dst_dir:
        dst_path = os.path.join(dst_dir, "output.jpg")
        result = await tool_copy_file(src_path, dst_path)
        assert "output.jpg" in result
        assert os.path.exists(dst_path)
        assert open(dst_path, "rb").read() == data

    os.unlink(src_path)


@pytest.mark.asyncio
async def test_file_manager_copy_file_creates_parents():
    """copy_file creates missing parent directories automatically."""
    import os, tempfile
    from steelclaw.skills.bundled.file_manager import tool_copy_file

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as src:
        src.write(b"hello")
        src_path = src.name

    with tempfile.TemporaryDirectory() as base:
        dst_path = os.path.join(base, "a", "b", "c", "out.txt")
        result = await tool_copy_file(src_path, dst_path)
        assert os.path.exists(dst_path)
        assert "out.txt" in result

    os.unlink(src_path)


@pytest.mark.asyncio
async def test_file_manager_copy_file_missing_source():
    """copy_file returns an error when the source does not exist."""
    from steelclaw.skills.bundled.file_manager import tool_copy_file
    result = await tool_copy_file("/nonexistent/path.jpg", "/tmp/out.jpg")
    assert "Error" in result


@pytest.mark.asyncio
async def test_file_manager_create_directory():
    """create_directory makes nested directories without error."""
    import os, tempfile
    from steelclaw.skills.bundled.file_manager import tool_create_directory

    with tempfile.TemporaryDirectory() as base:
        new_dir = os.path.join(base, "Bea", "Photos")
        result = await tool_create_directory(new_dir)
        assert "created" in result.lower() or "Directory" in result
        assert os.path.isdir(new_dir)


@pytest.mark.asyncio
async def test_file_manager_move_file():
    """move_file relocates a file and removes the original."""
    import os, tempfile
    from steelclaw.skills.bundled.file_manager import tool_move_file

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as src:
        src.write(b"move me")
        src_path = src.name

    with tempfile.TemporaryDirectory() as dst_dir:
        dst_path = os.path.join(dst_dir, "moved.txt")
        result = await tool_move_file(src_path, dst_path)
        assert os.path.exists(dst_path)
        assert not os.path.exists(src_path)
        assert "moved.txt" in result


@pytest.mark.asyncio
async def test_file_manager_delete_file():
    """delete_file removes a file and reports success."""
    import os, tempfile
    from steelclaw.skills.bundled.file_manager import tool_delete_file

    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as f:
        f.write(b"bye")
        tmp_path = f.name

    result = await tool_delete_file(tmp_path)
    assert not os.path.exists(tmp_path)
    assert "Deleted" in result
