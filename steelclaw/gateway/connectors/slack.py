"""Slack connector — stub implementation."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.slack")


class SlackConnector(BaseConnector):
    platform_name = "slack"

    async def _run(self) -> None:
        logger.info("Slack connector running (stub — implement with slack-bolt)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("Slack send not implemented")
