"""Discord connector — uses discord.py's async gateway.

Slash command interactions (Application Commands) are handled via the
``on_interaction`` event and responded to through ``interaction.followup``
so that Discord never shows "The application did not respond".
"""

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
# Discord's hard limit for message / followup content
_DISCORD_MAX_LEN = 2000


class DiscordConnector(BaseConnector):
    platform_name = "discord"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._client = None
        # interaction_id → discord.Interaction, kept while a response is in-flight
        self._pending_interactions: dict[str, object] = {}

    async def register_commands(self) -> None:
        """Register global slash commands with Discord via the Application Commands REST API.

        Fetches the application ID from ``/users/@me`` then bulk-overwrites
        the global command list so users see the ``/`` autocomplete menu.
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
                    logger.warning(
                        "Discord: could not resolve application ID, skipping command registration"
                    )
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

        # ── Regular text messages ────────────────────────────────────────

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

        # ── Slash command interactions ────────────────────────────────────

        @client.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            """Handle Application Command (slash command) interactions.

            Discord requires an acknowledgment within **3 seconds** or it
            shows "The application did not respond."  We defer immediately,
            then process the command through the normal pipeline and send the
            result as a followup message.
            """
            if interaction.type != discord.InteractionType.application_command:
                return

            # Acknowledge immediately — this MUST happen within 3 seconds.
            try:
                await interaction.response.defer()
            except Exception:
                logger.warning(
                    "Discord: failed to defer interaction %s", interaction.id
                )
                return

            # Build the slash command content string from interaction data
            command_name = "/" + (interaction.data or {}).get("name", "")
            options = (interaction.data or {}).get("options", []) or []
            args = " ".join(
                str(o["value"])
                for o in options
                if o.get("value") is not None
            )
            content = f"{command_name} {args}".strip()

            channel_id = (
                str(interaction.channel_id)
                if interaction.channel_id
                else str(interaction.user.id)
            )
            user = interaction.user

            logger.info(
                "Discord: slash command interaction — command=%s user=%s channel=%s",
                command_name,
                user,
                channel_id,
            )

            # Store the interaction so send() can route the reply via followup
            interaction_id = str(interaction.id)
            self._pending_interactions[interaction_id] = interaction

            inbound = InboundMessage(
                platform="discord",
                platform_chat_id=channel_id,
                platform_user_id=str(user.id),
                platform_message_id=interaction_id,
                platform_username=str(user),
                content=content,
                is_group=interaction.guild is not None,
                is_mention=False,
            )

            try:
                await self.dispatch(inbound)
            except Exception:
                logger.exception(
                    "Discord: error processing slash command interaction %s", interaction_id
                )
                # Clean up and send an error followup if the normal send() never ran
                pending = self._pending_interactions.pop(interaction_id, None)
                if pending is not None:
                    try:
                        await interaction.followup.send(
                            "An error occurred while processing your command. Please try again."
                        )
                    except Exception:
                        logger.debug(
                            "Discord: could not send error followup for %s", interaction_id
                        )

        try:
            await client.start(token)
        except asyncio.CancelledError:
            await client.close()

    # ── Typing indicator ──────────────────────────────────────────────────────

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

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send(self, message: OutboundMessage) -> None:
        """Send an outbound message.

        If the outbound message is a reply to a slash command interaction
        (identified by ``reply_to_message_id`` matching a pending interaction
        ID), the response is sent via ``interaction.followup.send()`` instead
        of the normal channel ``send()``.  This is required for Discord slash
        commands to work correctly.
        """
        # Route through interaction followup when applicable
        if message.reply_to_message_id:
            interaction = self._pending_interactions.pop(
                message.reply_to_message_id, None
            )
            if interaction is not None:
                content = _truncate(message.content)
                try:
                    await interaction.followup.send(content)
                except Exception:
                    logger.exception(
                        "Discord: followup.send failed for interaction %s",
                        message.reply_to_message_id,
                    )
                return

        # Regular channel message (not a slash command interaction)
        if self._client is None:
            return
        channel_id = int(message.platform_chat_id)
        channel = self._client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self._client.fetch_channel(channel_id)
            except Exception:
                logger.warning("Discord: could not resolve channel %s", channel_id)
                return
        if hasattr(channel, "send"):
            await channel.send(_truncate(message.content))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _truncate(text: str) -> str:
    """Truncate text to Discord's 2 000-character message limit."""
    if len(text) <= _DISCORD_MAX_LEN:
        return text
    suffix = "\n…*(truncated)*"
    return text[: _DISCORD_MAX_LEN - len(suffix)] + suffix


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
