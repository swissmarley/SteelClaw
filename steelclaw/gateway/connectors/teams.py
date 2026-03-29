"""Microsoft Teams connector — Bot Framework REST API."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.teams")


class TeamsConnector(BaseConnector):
    """Microsoft Teams connector via Bot Framework v3 REST API.

    Config requires:
    - token: Bot app password (client secret)
    - extra.app_id: Microsoft App ID (Bot registration)
    - extra.tenant_id: Azure AD tenant ID (optional, for single-tenant)

    This connector works as a webhook receiver. The actual webhook
    endpoint should be registered at /gateway/teams/webhook in the FastAPI app.
    The Bot Framework sends activities via HTTP POST to the messaging endpoint.
    """

    platform_name = "teams"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._access_token: str = ""
        self._token_expires: float = 0

    async def _run(self) -> None:
        app_id = self.config.extra.get("app_id", "")
        app_password = self.config.token

        if not app_id or not app_password:
            logger.error("Teams app_id or app password not configured")
            return

        logger.info("Teams connector started (waiting for Bot Framework activities)")

        try:
            while True:
                try:
                    activity = await asyncio.wait_for(self._message_queue.get(), timeout=30)
                    await self._process_activity(activity)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def enqueue_activity(self, activity: dict) -> None:
        """Called by the webhook endpoint to enqueue incoming activities."""
        await self._message_queue.put(activity)

    async def _process_activity(self, activity: dict) -> None:
        """Process a Bot Framework activity."""
        activity_type = activity.get("type", "")
        if activity_type != "message":
            return

        from_data = activity.get("from", {})
        conversation = activity.get("conversation", {})

        inbound = InboundMessage(
            platform="teams",
            platform_chat_id=conversation.get("id", ""),
            platform_user_id=from_data.get("id", ""),
            platform_message_id=activity.get("id", ""),
            platform_username=from_data.get("name"),
            content=activity.get("text", ""),
            is_group=conversation.get("conversationType") == "groupChat",
            is_mention=bool(activity.get("entities", [])),
            raw=activity,
        )
        await self.dispatch(inbound)

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth token for Bot Framework."""
        import time

        if self._access_token and time.time() < self._token_expires:
            return self._access_token

        import httpx

        app_id = self.config.extra.get("app_id", "")
        app_password = self.config.token
        tenant_id = self.config.extra.get("tenant_id", "botframework.com")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": app_id,
                    "client_secret": app_password,
                    "scope": "https://api.botframework.com/.default",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 3600) - 60
            return self._access_token

    async def send(self, message: OutboundMessage) -> None:
        import httpx

        if not self.config.token or not self.config.extra.get("app_id"):
            logger.warning("Teams not fully configured, cannot send")
            return

        try:
            token = await self._get_access_token()
        except Exception:
            logger.exception("Failed to get Teams access token")
            return

        service_url = message.metadata.get("service_url", "https://smba.trafficmanager.net/amer/") if message.metadata else "https://smba.trafficmanager.net/amer/"
        conversation_id = message.platform_chat_id

        payload = {
            "type": "message",
            "text": message.content,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{service_url}v3/conversations/{conversation_id}/activities",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            if resp.status_code not in (200, 201):
                logger.error("Teams send failed: %s %s", resp.status_code, resp.text[:200])
