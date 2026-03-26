"""Discord connector — uses discord.py's async gateway."""

from __future__ import annotations

import asyncio
import logging

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.discord")


class DiscordConnector(BaseConnector):
    platform_name = "discord"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._client = None

    async def _run(self) -> None:
        try:
            import discord
        except ImportError:
            logger.error("discord.py is not installed — run: pip install 'steelclaw[discord]'")
            return

        token = self.config.token
        if not token:
            logger.error("Discord token not configured")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_message(message: discord.Message) -> None:
            if message.author == client.user:
                return

            is_group = message.guild is not None
            is_mention = client.user in message.mentions if client.user else False

            inbound = InboundMessage(
                platform="discord",
                platform_chat_id=str(message.channel.id),
                platform_user_id=str(message.author.id),
                platform_message_id=str(message.id),
                platform_username=str(message.author),
                content=message.content,
                is_group=is_group,
                is_mention=is_mention,
            )
            await self.dispatch(inbound)

        try:
            await client.start(token)
        except asyncio.CancelledError:
            await client.close()

    async def send(self, message: OutboundMessage) -> None:
        if self._client is None:
            return
        channel = self._client.get_channel(int(message.platform_chat_id))
        if channel and hasattr(channel, "send"):
            await channel.send(message.content)
