"""Slack connector — Socket Mode via websockets, REST API for sending."""

from __future__ import annotations

import asyncio
import json
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.slack")


class SlackConnector(BaseConnector):
    platform_name = "slack"

    async def _run(self) -> None:
        token = self.config.token  # Bot token (xoxb-...)
        app_token = self.config.extra.get("app_token", "")  # App-level token (xapp-...)

        if not token:
            logger.error("Slack bot token not configured")
            return
        if not app_token:
            logger.error("Slack app-level token not configured (needed for Socket Mode)")
            return

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return

        while True:
            try:
                await self._connect_and_listen(token, app_token)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Slack connection error, reconnecting in 5s")
                await asyncio.sleep(5)

    async def _connect_and_listen(self, token: str, app_token: str) -> None:
        import httpx

        # Get WebSocket URL via apps.connections.open
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://slack.com/api/apps.connections.open",
                headers={"Authorization": f"Bearer {app_token}"},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error("Failed to open Slack connection: %s", data.get("error"))
                await asyncio.sleep(10)
                return
            ws_url = data["url"]

        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed — run: pip install websockets")
            return

        async with websockets.connect(ws_url) as ws:
            async for raw in ws:
                payload = json.loads(raw)
                envelope_id = payload.get("envelope_id")

                # Acknowledge immediately
                if envelope_id:
                    await ws.send(json.dumps({"envelope_id": envelope_id}))

                # Process events_api type
                event_payload = payload.get("payload", {})
                event = event_payload.get("event", {})

                if event.get("type") == "message" and not event.get("bot_id") and not event.get("subtype"):
                    inbound = InboundMessage(
                        platform="slack",
                        platform_chat_id=event.get("channel", ""),
                        platform_user_id=event.get("user", ""),
                        platform_message_id=event.get("ts", ""),
                        content=event.get("text", ""),
                        is_group=event.get("channel_type") not in ("im", "mpim"),
                        is_mention=f"<@" in event.get("text", ""),
                    )
                    await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        token = self.config.token
        if not token:
            logger.warning("Slack bot token not configured, cannot send")
            return

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": message.platform_chat_id,
                    "text": message.content,
                    **({"thread_ts": message.reply_to_message_id} if message.reply_to_message_id else {}),
                },
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack send failed: %s", data.get("error"))
