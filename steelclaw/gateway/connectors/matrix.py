"""Matrix connector — uses Matrix Client-Server API via httpx (no nio dependency)."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.matrix")


class MatrixConnector(BaseConnector):
    """Matrix connector using the Client-Server API with long-polling sync.

    Config requires:
    - token: Access token
    - extra.homeserver: Homeserver URL (e.g., https://matrix.org)
    - extra.user_id: Bot user ID (e.g., @bot:matrix.org)
    """

    platform_name = "matrix"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._since: str = ""

    async def _run(self) -> None:
        token = self.config.token
        if not token:
            logger.error("Matrix access token not configured")
            return

        homeserver = self.config.extra.get("homeserver", "")
        if not homeserver:
            logger.error("Matrix homeserver URL not configured")
            return

        bot_user_id = self.config.extra.get("user_id", "")

        import httpx

        logger.info("Matrix connector started (syncing from %s)", homeserver)

        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0)) as client:
            # Initial sync to get since token
            resp = await client.get(
                f"{homeserver}/_matrix/client/r0/sync",
                headers={"Authorization": f"Bearer {token}"},
                params={"timeout": "0", "filter": '{"room":{"timeline":{"limit":0}}}'},
            )
            if resp.status_code == 200:
                self._since = resp.json().get("next_batch", "")

            while True:
                try:
                    params = {"timeout": "30000"}
                    if self._since:
                        params["since"] = self._since

                    resp = await client.get(
                        f"{homeserver}/_matrix/client/r0/sync",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params,
                        timeout=35,
                    )
                    if resp.status_code != 200:
                        logger.warning("Matrix sync returned %d", resp.status_code)
                        await asyncio.sleep(5)
                        continue

                    data = resp.json()
                    self._since = data.get("next_batch", self._since)

                    # Process room events
                    rooms = data.get("rooms", {}).get("join", {})
                    for room_id, room_data in rooms.items():
                        for event in room_data.get("timeline", {}).get("events", []):
                            if (event.get("type") == "m.room.message"
                                    and event.get("sender") != bot_user_id):
                                content = event.get("content", {})
                                if content.get("msgtype") == "m.text":
                                    inbound = InboundMessage(
                                        platform="matrix",
                                        platform_chat_id=room_id,
                                        platform_user_id=event.get("sender", ""),
                                        platform_message_id=event.get("event_id", ""),
                                        content=content.get("body", ""),
                                        is_group=True,
                                        is_mention=bot_user_id in content.get("body", ""),
                                    )
                                    await self.dispatch(inbound)

                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("Matrix sync error")
                    await asyncio.sleep(5)

    async def send(self, message: OutboundMessage) -> None:
        import httpx
        import uuid

        token = self.config.token
        homeserver = self.config.extra.get("homeserver", "")

        if not token or not homeserver:
            logger.warning("Matrix not fully configured, cannot send")
            return

        txn_id = uuid.uuid4().hex

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{homeserver}/_matrix/client/r0/rooms/{message.platform_chat_id}/send/m.room.message/{txn_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "msgtype": "m.text",
                    "body": message.content,
                },
            )
            if resp.status_code not in (200, 201):
                logger.error("Matrix send failed: %s", resp.text[:200])
