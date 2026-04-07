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
        # (channel_id, call_id) → discord message object for ephemeral tool status
        self._tool_status_msgs: dict[tuple[str, str], object] = {}

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
            """Handle Application Command (slash command) and button interactions.

            Discord requires an acknowledgment within **3 seconds** or it
            shows "The application did not respond."  We defer immediately,
            then process the command through the normal pipeline and send the
            result as a followup message.
            """
            # Handle button clicks for permission requests
            if interaction.type == discord.InteractionType.component:
                custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
                if custom_id.startswith("perm:"):
                    await self._handle_permission_button(interaction, custom_id)
                    return
                return  # Unknown component type

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

    async def send_tool_status(
        self, chat_id: str, tool_name: str, call_id: str, label: str | None = None
    ) -> None:
        """Send an ephemeral-style tool status message to the Discord channel."""
        if self._client is None:
            return
        try:
            channel_id = int(chat_id)
            channel = self._client.get_channel(channel_id)
            if channel is None:
                channel = await self._client.fetch_channel(channel_id)
            if channel and hasattr(channel, "send"):
                text = f"⚙ Running: **{tool_name}**"
                if label:
                    text += f"\n*{label}*"
                msg = await channel.send(text)
                self._tool_status_msgs[(chat_id, call_id)] = msg
        except Exception:
            logger.debug("Failed to send tool status to Discord channel %s", chat_id)

    async def clear_tool_status(self, chat_id: str, call_id: str) -> None:
        """Delete the ephemeral tool status message."""
        msg = self._tool_status_msgs.pop((chat_id, call_id), None)
        if msg is None:
            return
        try:
            await msg.delete()
        except Exception:
            logger.debug("Failed to delete Discord tool status message in channel %s", chat_id)

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

    async def send_permission_request(self, chat_id: str, request_data: dict) -> None:
        """Send an interactive permission request with Discord UI buttons."""
        try:
            import discord
        except ImportError:
            # Fallback to default text message
            await super().send_permission_request(chat_id, request_data)
            return

        if self._client is None:
            return

        request_id = request_data.get("request_id", "")
        command = request_data.get("command", "unknown command")
        timeout = request_data.get("timeout_seconds", 300)
        context = request_data.get("context")

        # Build message text
        lines = [
            "🔒 **Permission Request**",
            f"```\n{command}\n```",
            f"Timeout: {timeout}s",
        ]
        if context:
            lines.insert(2, f"Context: {context}")

        text = "\n".join(lines)

        # Create Discord UI View with buttons
        view = discord.ui.View(timeout=timeout)

        approve_once_btn = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Approve Once",
            custom_id=f"perm:{request_id}:approve_once",
        )
        approve_session_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Approve Session",
            custom_id=f"perm:{request_id}:approve_session",
        )
        deny_btn = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Deny",
            custom_id=f"perm:{request_id}:deny",
        )

        view.add_item(approve_once_btn)
        view.add_item(approve_session_btn)
        view.add_item(deny_btn)

        # Store pending permission requests
        if not hasattr(self, "_pending_permissions"):
            self._pending_permissions = {}

        # If chat_id is empty or not a Discord channel ID (e.g., a UUID from WebSocket),
        # we can't send to a specific channel. For now, just log and return.
        # In the future, we could maintain a list of active Discord channels to broadcast to.
        if not chat_id:
            logger.debug("No Discord chat_id provided for permission request, skipping Discord broadcast")
            return

        try:
            # Try to parse as Discord channel ID (integer)
            channel_id = int(chat_id)
        except (ValueError, TypeError):
            # Not a Discord channel ID (probably a WebSocket UUID), skip
            logger.debug("chat_id '%s' is not a Discord channel ID, skipping Discord broadcast", chat_id)
            return

        try:
            channel = self._client.get_channel(channel_id)
            if channel is None:
                channel = await self._client.fetch_channel(channel_id)

            if channel and hasattr(channel, "send"):
                msg = await channel.send(text, view=view)
                self._pending_permissions[request_id] = msg
        except Exception:
            logger.exception("Failed to send permission request to Discord")

    async def _on_permission_response(
        self, request_id: str, decision, user_id: str
    ) -> None:
        """Handle permission response from Discord button click."""
        # First call the parent to resolve with the broadcaster
        await super()._on_permission_response(request_id, decision, user_id)

        # Update the message to show the result
        if hasattr(self, "_pending_permissions"):
            msg = self._pending_permissions.pop(request_id, None)
            if msg and hasattr(msg, "edit"):
                try:
                    from steelclaw.security.permission_models import PermissionDecision

                    result_text = "🔒 Permission Request\n"
                    if decision == PermissionDecision.APPROVE_ONCE:
                        result_text += f"✅ Approved by <@{user_id}>"
                    elif decision == PermissionDecision.APPROVE_SESSION:
                        result_text += f"✅ Approved for session by <@{user_id}>"
                    else:
                        result_text += f"❌ Denied by <@{user_id}>"

                    await msg.edit(content=result_text, view=None)
                except Exception:
                    logger.debug("Failed to update Discord permission message")

    async def _handle_permission_button(
        self, interaction, custom_id: str
    ) -> None:
        """Handle a permission button click from Discord."""
        try:
            import discord
        except ImportError:
            return

        # Parse custom_id: perm:request_id:decision
        parts = custom_id.split(":")
        if len(parts) < 3:
            return

        request_id = parts[1]
        decision_str = parts[2]
        user_id = str(interaction.user.id) if interaction.user else "unknown"

        # Map decision to enum
        from steelclaw.security.permission_models import PermissionDecision
        try:
            decision = PermissionDecision(decision_str)
        except ValueError:
            decision = PermissionDecision.DENY

        # Acknowledge the button click immediately
        try:
            await interaction.response.defer()
        except Exception:
            pass

        # Forward to the broadcaster
        await self._on_permission_response(request_id, decision, user_id)


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
