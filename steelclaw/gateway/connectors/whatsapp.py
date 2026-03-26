"""WhatsApp connector — stub implementation."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.whatsapp")


class WhatsAppConnector(BaseConnector):
    platform_name = "whatsapp"

    async def _run(self) -> None:
        logger.info("WhatsApp connector running (stub — implement with Cloud API webhooks)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("WhatsApp send not implemented")
