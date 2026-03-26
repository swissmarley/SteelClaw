"""Built-in WebSocket connector.

The actual WebSocket handling lives in ``gateway.router`` (FastAPI manages the
connection lifecycle).  This connector exists so the registry can track it and
the send path works uniformly.
"""

from __future__ import annotations

import asyncio

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import OutboundMessage


class WebSocketConnector(BaseConnector):
    platform_name = "websocket"

    async def _run(self) -> None:
        # WebSocket connections are managed by the FastAPI endpoint, not a polling loop.
        # Keep the task alive so the registry considers this connector "running".
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return

    async def send(self, message: OutboundMessage) -> None:
        # Sending is handled inline in the WebSocket endpoint; this is a no-op fallback.
        pass
