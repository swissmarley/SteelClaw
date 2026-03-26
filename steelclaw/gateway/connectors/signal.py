"""Signal connector — stub implementation."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.signal")


class SignalConnector(BaseConnector):
    platform_name = "signal"

    async def _run(self) -> None:
        logger.info("Signal connector running (stub — implement with signal-cli REST API)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("Signal send not implemented")
