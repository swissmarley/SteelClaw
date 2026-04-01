"""Mattermost connector — WebSocket event stream + REST API."""

from __future__ import annotations

import asyncio
import json
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.mattermost")


class MattermostConnector(BaseConnector):
    """Mattermost connector via WebSocket API v4.

    Config requires:
    - token: Personal access token or bot token
    - extra.url: Mattermost server URL (e.g., https://mattermost.example.com)
    """

    platform_name = "mattermost"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._bot_user_id: str = ""

    async def _run(self) -> None:
        token = self.config.token
        if not token:
            logger.error("Mattermost token not configured")
            return

        server_url = self.config.extra.get("url", "")
        if not server_url:
            logger.error("Mattermost server URL not configured")
            return

        import httpx

        # Get bot user ID
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{server_url}/api/v4/users/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                self._bot_user_id = resp.json().get("id", "")

        # Connect WebSocket
        ws_url = server_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/api/v4/websocket"

        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed — run: pip install websockets")
            return

        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    # Authenticate
                    await ws.send(json.dumps({
                        "seq": 1,
                        "action": "authentication_challenge",
                        "data": {"token": token},
                    }))

                    async for raw in ws:
                        event = json.loads(raw)
                        if event.get("event") == "posted":
                            await self._handle_post(event)

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Mattermost connection error, reconnecting in 5s")
                await asyncio.sleep(5)

    async def _handle_post(self, event: dict) -> None:
        data = event.get("data", {})
        post_json = data.get("post", "")
        if not post_json:
            return

        post = json.loads(post_json) if isinstance(post_json, str) else post_json

        # Ignore own messages
        if post.get("user_id") == self._bot_user_id:
            return

        channel_type = data.get("channel_type", "O")
        inbound = InboundMessage(
            platform="mattermost",
            platform_chat_id=post.get("channel_id", ""),
            platform_user_id=post.get("user_id", ""),
            platform_message_id=post.get("id", ""),
            platform_username=data.get("sender_name", ""),
            content=post.get("message", ""),
            is_group=channel_type in ("O", "P"),  # Open or Private channel
            is_mention=f"@{data.get('sender_name', '')}" in post.get("message", ""),
        )
        await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        token = self.config.token
        server_url = self.config.extra.get("url", "")

        if not token or not server_url:
            logger.warning("Mattermost not fully configured, cannot send")
            return

        payload = {
            "channel_id": message.platform_chat_id,
            "message": message.content,
        }
        if message.reply_to_message_id:
            payload["root_id"] = message.reply_to_message_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{server_url}/api/v4/posts",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            if resp.status_code not in (200, 201):
                logger.error("Mattermost send failed: %s", resp.text[:200])
