"""Telegram connector — long-polling via httpx."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import os

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.telegram")


class TelegramConnector(BaseConnector):
    platform_name = "telegram"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._offset = 0

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
        entities = msg_data.get("entities", [])
        is_mention = any(e["type"] in ("mention", "text_mention") for e in entities)
        sender = msg_data.get("from", {})

        # Determine message content — text or transcribed voice
        content = msg_data.get("text")

        if content is None and msg_data.get("voice"):
            content = await self._transcribe_voice(msg_data["voice"])

        if not content:
            return

        inbound = InboundMessage(
            platform="telegram",
            platform_chat_id=str(chat["id"]),
            platform_user_id=str(sender.get("id", chat["id"])),
            platform_message_id=str(msg_data["message_id"]),
            platform_username=sender.get("username"),
            content=content,
            is_group=is_group,
            is_mention=is_mention,
            raw=update,
        )
        await self.dispatch(inbound)

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
