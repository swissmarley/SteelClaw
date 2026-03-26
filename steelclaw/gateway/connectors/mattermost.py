"""Mattermost connector — stub implementation."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.mattermost")


class MattermostConnector(BaseConnector):
    platform_name = "mattermost"

    async def _run(self) -> None:
        logger.info("Mattermost connector running (stub — implement with WebSocket API)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("Mattermost send not implemented")
