"""Matrix connector — stub implementation."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage

logger = logging.getLogger("steelclaw.gateway.matrix")


class MatrixConnector(BaseConnector):
    platform_name = "matrix"

    async def _run(self) -> None:
        logger.info("Matrix connector running (stub — implement with matrix-nio)")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        logger.warning("Matrix send not implemented")
