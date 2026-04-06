"""Discord connector — uses discord.py's async gateway."""

from __future__ import annotations

import asyncio
import logging

import httpx

from steelclaw.gateway.base import BaseConnector
from steelclaw.gateway.attachments import build_attachment_dict, transcribe_audio_attachment
from steelclaw.gateway.commands import SLASH_COMMANDS
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.discord")

_DISCORD_API = "https://discord.com/api/v10"


class DiscordConnector(BaseConnector):
    platform_name = "discord"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._client = None

    async def register_commands(self) -> None:
        """Register global slash commands with Discord via the Application Commands REST API.

        Fetches the application ID from the ``/users/@me`` endpoint then calls
        ``/applications/{id}/commands`` to bulk-overwrite the global command list.
        """
        token = self.config.token
        if not token:
            return

        headers = {"Authorization": f"Bot {token}"}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Resolve application (bot) ID
                me_resp = await client.get(f"{_DISCORD_API}/users/@me", headers=headers)
                me_resp.raise_for_status()
                application_id = me_resp.json().get("id")
                if not application_id:
                    logger.warning("Discord: could not resolve application ID, skipping command registration")
                    return

                # Build command payload (CHAT_INPUT = type 1)
                commands = [
                    {"name": cmd["name"], "description": cmd["description"], "type": 1}
                    for cmd in SLASH_COMMANDS
                ]

                # Bulk-overwrite global application commands
                resp = await client.put(
                    f"{_DISCORD_API}/applications/{application_id}/commands",
                    headers=headers,
                    json=commands,
                )
                resp.raise_for_status()
                logger.info(
                    "Discord: registered %d global slash commands (application_id=%s)",
                    len(commands),
                    application_id,
                )
        except Exception:
            logger.exception("Discord: failed to register slash commands")

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

            content = message.content or ""

            # Process Discord file attachments
            attachments = await _collect_discord_attachments(message.attachments)

            # Skip if neither text nor attachments were found
            if not content and not attachments:
                return

            # Use descriptive placeholder when file arrives without a caption
            if not content and attachments:
                names = ", ".join(a["filename"] for a in attachments)
                content = f"[File attachment: {names}]"

            inbound = InboundMessage(
                platform="discord",
                platform_chat_id=str(message.channel.id),
                platform_user_id=str(message.author.id),
                platform_message_id=str(message.id),
                platform_username=str(message.author),
                content=content,
                attachments=attachments if attachments else None,
                is_group=is_group,
                is_mention=is_mention,
            )
            await self.dispatch(inbound)

        try:
            await client.start(token)
        except asyncio.CancelledError:
            await client.close()

    async def send_typing(self, chat_id: str) -> None:
        if self._client is None:
            return
        channel_id = int(chat_id)
        channel = self._client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self._client.fetch_channel(channel_id)
            except Exception:
                return
        if channel and hasattr(channel, "typing"):
            try:
                async with channel.typing():
                    pass
            except Exception:
                logger.debug("Failed to send typing indicator to %s", chat_id)

    async def send(self, message: OutboundMessage) -> None:
        if self._client is None:
            return
        channel_id = int(message.platform_chat_id)
        channel = self._client.get_channel(channel_id)
        if channel is None:
            # DM channels are often not in the cache — fetch from API
            try:
                channel = await self._client.fetch_channel(channel_id)
            except Exception:
                logger.warning("Discord: could not resolve channel %s", channel_id)
                return
        if hasattr(channel, "send"):
            await channel.send(message.content)


# ── Attachment helpers ───────────────────────────────────────────────────────

async def _collect_discord_attachments(discord_attachments) -> list[dict]:
    """Download Discord attachment objects and return normalised attachment dicts."""
    result: list[dict] = []
    for att in discord_attachments:
        filename = att.filename
        content_type = getattr(att, "content_type", None)
        url = att.url
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
            att_dict = build_attachment_dict(filename=filename, mime=content_type, data=data)
            # Transcribe audio/voice messages (e.g. OGG voice notes)
            if att_dict["category"] == "audio" and not att_dict.get("text_content"):
                transcription = await transcribe_audio_attachment(data, filename)
                if transcription:
                    att_dict["text_content"] = transcription
            result.append(att_dict)
        except Exception:
            logger.exception("Failed to download Discord attachment '%s'", filename)
            # Include metadata-only entry so the agent knows a file was sent
            result.append(
                build_attachment_dict(filename=filename, mime=content_type, data=None)
            )
    return result
