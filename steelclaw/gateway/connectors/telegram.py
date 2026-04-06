"""Telegram connector — long-polling via httpx."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import os

from steelclaw.gateway.base import BaseConnector
from steelclaw.gateway.attachments import build_attachment_dict, transcribe_audio_attachment
from steelclaw.gateway.commands import SLASH_COMMANDS
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.telegram")


class TelegramConnector(BaseConnector):
    platform_name = "telegram"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._offset = 0
        # Maps (chat_id, call_id) → telegram message_id for ephemeral tool status msgs
        self._tool_status_msgs: dict[tuple[str, str], int] = {}

    async def register_commands(self) -> None:
        """Register slash commands with Telegram via setMyCommands API."""
        import httpx

        token = self.config.token
        if not token:
            return

        commands = [
            {"command": cmd["name"], "description": cmd["description"]}
            for cmd in SLASH_COMMANDS
        ]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/setMyCommands",
                    json={"commands": commands},
                )
                data = resp.json()
                if data.get("ok"):
                    logger.info(
                        "Telegram: registered %d slash commands via setMyCommands", len(commands)
                    )
                else:
                    logger.warning(
                        "Telegram: setMyCommands failed: %s", data.get("description", data)
                    )
        except Exception:
            logger.exception("Telegram: failed to register slash commands")

    async def _run(self) -> None:
        import httpx

        token = self.config.token
        if not token:
            logger.error("Telegram token not configured")
            return

        base = f"https://api.telegram.org/bot{token}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0)) as client:
            while True:
                try:
                    resp = await client.get(
                        f"{base}/getUpdates",
                        params={"offset": self._offset, "timeout": 30},
                    )
                    resp.raise_for_status()
                    for update in resp.json().get("result", []):
                        self._offset = update["update_id"] + 1
                        await self._handle_update(update)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Telegram polling error")
                    await asyncio.sleep(5)

    async def _handle_update(self, update: dict) -> None:
        msg_data = update.get("message") or update.get("channel_post")
        if not msg_data:
            return

        chat = msg_data["chat"]
        is_group = chat["type"] in ("group", "supergroup")
        # Check both entities (text messages) and caption_entities (media messages)
        entities = msg_data.get("entities", []) + msg_data.get("caption_entities", [])
        is_mention = any(e["type"] in ("mention", "text_mention") for e in entities)
        sender = msg_data.get("from", {})

        # Determine text content
        content = msg_data.get("text") or msg_data.get("caption") or ""

        # Handle voice → transcribe to text
        if not content and msg_data.get("voice"):
            content = await self._transcribe_voice(msg_data["voice"]) or ""

        # Handle file attachments (photo, document, audio, video, animation, sticker)
        attachments = await self._extract_attachments(msg_data)

        # Skip if neither text nor attachments were found
        if not content and not attachments:
            return

        # Use descriptive placeholder when file arrives without caption
        if not content and attachments:
            names = ", ".join(a["filename"] for a in attachments)
            content = f"[File attachment: {names}]"

        inbound = InboundMessage(
            platform="telegram",
            platform_chat_id=str(chat["id"]),
            platform_user_id=str(sender.get("id", chat["id"])),
            platform_message_id=str(msg_data["message_id"]),
            platform_username=sender.get("username"),
            content=content,
            attachments=attachments if attachments else None,
            is_group=is_group,
            is_mention=is_mention,
            raw=update,
        )
        await self.dispatch(inbound)

    # ── Attachment extraction ────────────────────────────────────────────────

    async def _extract_attachments(self, msg_data: dict) -> list[dict]:
        """Detect and download any file attachments from a Telegram message."""
        attachments: list[dict] = []

        # Photo — take the largest size (last element in the array)
        if msg_data.get("photo"):
            photo_sizes = msg_data["photo"]
            best = photo_sizes[-1]  # largest resolution
            att = await self._download_attachment(
                file_id=best["file_id"],
                filename="photo.jpg",
                mime="image/jpeg",
            )
            if att:
                attachments.append(att)

        # Document (PDF, CSV, Word, plain text, etc.)
        elif msg_data.get("document"):
            doc = msg_data["document"]
            filename = doc.get("file_name") or "document"
            mime = doc.get("mime_type")
            att = await self._download_attachment(
                file_id=doc["file_id"],
                filename=filename,
                mime=mime,
            )
            if att:
                attachments.append(att)

        # Audio file
        elif msg_data.get("audio"):
            audio = msg_data["audio"]
            filename = audio.get("file_name") or "audio.mp3"
            mime = audio.get("mime_type") or "audio/mpeg"
            att = await self._download_attachment(
                file_id=audio["file_id"],
                filename=filename,
                mime=mime,
            )
            if att:
                attachments.append(att)

        # Video file
        elif msg_data.get("video"):
            video = msg_data["video"]
            filename = video.get("file_name") or "video.mp4"
            mime = video.get("mime_type") or "video/mp4"
            att = await self._download_attachment(
                file_id=video["file_id"],
                filename=filename,
                mime=mime,
            )
            if att:
                attachments.append(att)

        # Animation (GIF)
        elif msg_data.get("animation"):
            anim = msg_data["animation"]
            filename = anim.get("file_name") or "animation.gif"
            mime = anim.get("mime_type") or "image/gif"
            att = await self._download_attachment(
                file_id=anim["file_id"],
                filename=filename,
                mime=mime,
            )
            if att:
                attachments.append(att)

        # Sticker (WebP image)
        elif msg_data.get("sticker"):
            sticker = msg_data["sticker"]
            att = await self._download_attachment(
                file_id=sticker["file_id"],
                filename="sticker.webp",
                mime="image/webp",
            )
            if att:
                attachments.append(att)

        return attachments

    async def _download_attachment(
        self,
        file_id: str,
        filename: str,
        mime: str | None,
    ) -> dict | None:
        """Download a Telegram file and return a normalised attachment dict."""
        import httpx

        token = self.config.token
        if not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Resolve file path
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getFile",
                    params={"file_id": file_id},
                )
                resp.raise_for_status()
                file_path = resp.json().get("result", {}).get("file_path")
                if not file_path:
                    logger.warning("Telegram getFile returned no file_path for %s", file_id)
                    return None

                # Download file bytes
                file_resp = await client.get(
                    f"https://api.telegram.org/file/bot{token}/{file_path}",
                )
                file_resp.raise_for_status()
                data = file_resp.content

            att_dict = build_attachment_dict(filename=filename, mime=mime, data=data)
            # Transcribe audio files that aren't already handled by _transcribe_voice
            if att_dict["category"] == "audio" and not att_dict.get("text_content"):
                transcription = await transcribe_audio_attachment(data, filename)
                if transcription:
                    att_dict["text_content"] = transcription
            return att_dict

        except Exception:
            logger.exception("Failed to download Telegram file %s", file_id)
            # Return metadata-only attachment so the agent still knows a file was sent
            return build_attachment_dict(filename=filename, mime=mime, data=None)

    # ── Voice transcription ──────────────────────────────────────────────────

    async def _transcribe_voice(self, voice: dict) -> str | None:
        """Download a Telegram voice message and transcribe it via Whisper."""
        import httpx
        from steelclaw.settings import VoiceSettings
        from steelclaw.voice.transcription import Transcriber

        token = self.config.token
        file_id = voice.get("file_id")
        if not file_id or not token:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Step 1: resolve file path
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getFile",
                    params={"file_id": file_id},
                )
                resp.raise_for_status()
                file_path = resp.json().get("result", {}).get("file_path")
                if not file_path:
                    logger.warning("Telegram getFile returned no file_path for %s", file_id)
                    return None

                # Step 2: download the audio
                audio_resp = await client.get(
                    f"https://api.telegram.org/file/bot{token}/{file_path}",
                )
                audio_resp.raise_for_status()

            # Step 3: transcribe from a temp file
            suffix = os.path.splitext(file_path)[1] or ".oga"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_resp.content)
                tmp_path = tmp.name

            try:
                transcriber = Transcriber(VoiceSettings())
                result = await transcriber.transcribe(tmp_path)
                if result.ok:
                    logger.info("Transcribed Telegram voice (%s): %d chars", file_id, len(result.text))
                    return result.text
                else:
                    logger.warning("Transcription failed for %s: %s", file_id, result.error)
                    return None
            finally:
                os.unlink(tmp_path)

        except Exception:
            logger.exception("Error transcribing Telegram voice message %s", file_id)
            return None

    async def send_typing(self, chat_id: str) -> None:
        import httpx

        token = self.config.token
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                )
        except Exception:
            logger.debug("Failed to send typing indicator to %s", chat_id)

    async def send_tool_status(
        self, chat_id: str, tool_name: str, call_id: str, label: str | None = None
    ) -> None:
        """Send an ephemeral status message showing which tool is running."""
        import httpx

        token = self.config.token
        if not token:
            return
        # Use plain text — tool names often contain underscores (e.g. web_search)
        # which Telegram's Markdown parser misinterprets as italic markers.
        text = f"⚙ Running: {tool_name}"
        if label:
            text += f"\n{label}"
        payload: dict = {"chat_id": chat_id, "text": text}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                data = resp.json()
                if data.get("ok"):
                    msg_id = data["result"]["message_id"]
                    self._tool_status_msgs[(chat_id, call_id)] = msg_id
                else:
                    logger.debug(
                        "Telegram sendMessage for tool status failed: %s",
                        data.get("description"),
                    )
        except Exception:
            logger.debug("Failed to send tool status message to %s", chat_id)

    async def clear_tool_status(self, chat_id: str, call_id: str) -> None:
        """Delete the ephemeral tool status message."""
        import httpx

        token = self.config.token
        msg_id = self._tool_status_msgs.pop((chat_id, call_id), None)
        if not token or msg_id is None:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/deleteMessage",
                    json={"chat_id": chat_id, "message_id": msg_id},
                )
        except Exception:
            logger.debug("Failed to delete tool status message %s in chat %s", msg_id, chat_id)

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        token = self.config.token
        payload: dict = {
            "chat_id": message.platform_chat_id,
            "text": message.content,
        }
        if message.reply_to_message_id:
            payload["reply_to_message_id"] = message.reply_to_message_id

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            )
