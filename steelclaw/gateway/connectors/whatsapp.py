"""WhatsApp connector — Cloud API via webhook polling."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.whatsapp")


class WhatsAppConnector(BaseConnector):
    """WhatsApp Business Cloud API connector.

    Config requires:
    - token: Permanent access token
    - extra.phone_number_id: WhatsApp Business phone number ID
    - extra.verify_token: Webhook verification token

    This connector polls a local webhook queue. The actual webhook
    endpoint should be registered via the FastAPI app at /gateway/whatsapp/webhook.
    """

    platform_name = "whatsapp"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def _run(self) -> None:
        token = self.config.token
        if not token:
            logger.error("WhatsApp access token not configured")
            return

        phone_number_id = self.config.extra.get("phone_number_id", "")
        if not phone_number_id:
            logger.error("WhatsApp phone_number_id not configured")
            return

        logger.info("WhatsApp connector started (waiting for webhook messages)")

        try:
            while True:
                # Process messages from the webhook queue
                try:
                    webhook_data = await asyncio.wait_for(self._message_queue.get(), timeout=30)
                    await self._process_webhook(webhook_data)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def enqueue_webhook(self, data: dict) -> None:
        """Called by the webhook endpoint to enqueue incoming messages."""
        await self._message_queue.put(data)

    async def _process_webhook(self, data: dict) -> None:
        """Process a WhatsApp Cloud API webhook payload."""
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        continue

                    contact = value.get("contacts", [{}])[0]
                    inbound = InboundMessage(
                        platform="whatsapp",
                        platform_chat_id=msg.get("from", ""),
                        platform_user_id=msg.get("from", ""),
                        platform_message_id=msg.get("id", ""),
                        platform_username=contact.get("profile", {}).get("name"),
                        content=msg.get("text", {}).get("body", ""),
                        is_group=False,
                        is_mention=False,
                        raw=data,
                    )
                    await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        token = self.config.token
        phone_number_id = self.config.extra.get("phone_number_id", "")

        if not token or not phone_number_id:
            logger.warning("WhatsApp not fully configured, cannot send")
            return

        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": message.platform_chat_id,
            "type": "text",
            "text": {"body": message.content},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("WhatsApp send failed: %s %s", resp.status_code, resp.text[:200])
