"""Signal connector — uses signal-cli REST API (JSON-RPC)."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.signal")


class SignalConnector(BaseConnector):
    """Signal connector using signal-cli REST API.

    Config requires:
    - token: Signal phone number (e.g., +1234567890)
    - extra.api_url: signal-cli REST API URL (default: http://localhost:8080)
    """

    platform_name = "signal"

    async def _run(self) -> None:
        phone = self.config.token
        if not phone:
            logger.error("Signal phone number not configured")
            return

        api_url = self.config.extra.get("api_url", "http://localhost:8080")

        import httpx

        logger.info("Signal connector started (polling %s)", api_url)

        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0)) as client:
            while True:
                try:
                    # signal-cli REST API: receive messages
                    resp = await client.get(
                        f"{api_url}/v1/receive/{phone}",
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        messages = resp.json()
                        for msg in messages:
                            await self._handle_message(msg)
                    elif resp.status_code == 204:
                        pass  # No new messages
                    else:
                        logger.warning("Signal receive returned %d", resp.status_code)
                        await asyncio.sleep(5)
                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("Signal polling error")
                    await asyncio.sleep(5)

    async def _handle_message(self, msg: dict) -> None:
        """Process a signal-cli message envelope."""
        envelope = msg.get("envelope", {})
        data_msg = envelope.get("dataMessage")
        if not data_msg or not data_msg.get("message"):
            return

        source = envelope.get("source", "")
        group_info = data_msg.get("groupInfo")

        inbound = InboundMessage(
            platform="signal",
            platform_chat_id=group_info.get("groupId", source) if group_info else source,
            platform_user_id=source,
            platform_message_id=str(envelope.get("timestamp", "")),
            content=data_msg["message"],
            is_group=group_info is not None,
            is_mention=False,
            raw=msg,
        )
        await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        phone = self.config.token
        api_url = self.config.extra.get("api_url", "http://localhost:8080")

        if not phone:
            logger.warning("Signal phone not configured, cannot send")
            return

        payload = {
            "message": message.content,
            "number": phone,
            "recipients": [message.platform_chat_id],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{api_url}/v2/send", json=payload)
            if resp.status_code not in (200, 201):
                logger.error("Signal send failed: %s %s", resp.status_code, resp.text[:200])
