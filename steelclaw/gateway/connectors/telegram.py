"""Telegram connector — long-polling via httpx."""

from __future__ import annotations

import asyncio
import logging

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
        if not msg_data or not msg_data.get("text"):
            return

        chat = msg_data["chat"]
        is_group = chat["type"] in ("group", "supergroup")

        entities = msg_data.get("entities", [])
        is_mention = any(e["type"] in ("mention", "text_mention") for e in entities)

        sender = msg_data.get("from", {})
        inbound = InboundMessage(
            platform="telegram",
            platform_chat_id=str(chat["id"]),
            platform_user_id=str(sender.get("id", chat["id"])),
            platform_message_id=str(msg_data["message_id"]),
            platform_username=sender.get("username"),
            content=msg_data["text"],
            is_group=is_group,
            is_mention=is_mention,
            raw=update,
        )
        await self.dispatch(inbound)

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
