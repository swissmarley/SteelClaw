"""iMessage connector — stub implementation (macOS only)."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.imessage")


class IMessageConnector(BaseConnector):
    platform_name = "imessage"

    async def _run(self) -> None:
        logger.info("iMessage connector running (stub — implement with AppleScript bridge)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("iMessage send not implemented")
