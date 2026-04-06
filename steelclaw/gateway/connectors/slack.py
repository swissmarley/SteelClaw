"""Slack connector — Socket Mode via websockets, REST API for sending."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from steelclaw.gateway.base import BaseConnector
from steelclaw.gateway.attachments import build_attachment_dict, transcribe_audio_attachment
from steelclaw.gateway.commands import SLASH_COMMANDS
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.slack")

# Subtypes we handle (file_share) in addition to plain messages (no subtype)
_HANDLED_SUBTYPES = frozenset({"file_share"})


class SlackConnector(BaseConnector):
    platform_name = "slack"

    async def register_commands(self) -> None:
        """Log the slash commands that must be configured in the Slack app manifest.

        Slack slash commands are registered via the app configuration (App Manifest /
        Slash Commands settings page) rather than at runtime via the API.  This method
        emits an INFO log listing every command so that operators know exactly which
        commands to add when setting up the Slack app.
        """
        names = ", ".join(f"/{cmd['name']}" for cmd in SLASH_COMMANDS)
        logger.info(
            "Slack: configure the following slash commands in your Slack app settings: %s", names
        )

    async def verify(self) -> str | None:
        """Validate Slack tokens via auth.test before starting the connector."""
        token = self.config.token
        app_token = (self.config.model_extra or {}).get("app_token", "")

        if not token:
            return "Slack bot token not configured (expected xoxb-...)"
        if not app_token:
            return "Slack app-level token not configured (expected xapp-...)"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                data = resp.json()
                if not data.get("ok"):
                    return f"auth.test failed: {data.get('error', 'unknown')}"
                logger.info(
                    "Slack auth.test OK — bot: %s, team: %s",
                    data.get("user"),
                    data.get("team"),
                )
        except Exception as exc:
            return f"Slack connection error: {exc}"

        return None

    async def _run(self) -> None:
        token = self.config.token  # Bot token (xoxb-...)
        app_token = (self.config.model_extra or {}).get("app_token", "")  # App-level token (xapp-...)

        if not token:
            self.last_error = "Bot token not configured (expected xoxb-...)"
            logger.error("Slack bot token not configured")
            return
        if not app_token:
            self.last_error = (
                "App-level token not configured (expected xapp-...). "
                "Required for Socket Mode — create one in your Slack app under Settings → App-Level Tokens."
            )
            logger.error("Slack app-level token not configured (needed for Socket Mode)")
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

        logger.info("Slack Socket Mode connected")
        async with websockets.connect(ws_url) as ws:
            async for raw in ws:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Slack: received non-JSON frame, skipping")
                    continue

                envelope_id = payload.get("envelope_id")
                envelope_type = payload.get("type")

                # Acknowledge immediately
                if envelope_id:
                    await ws.send(json.dumps({"envelope_id": envelope_id}))

                logger.info("Slack frame received: envelope_type=%s envelope_id=%s", envelope_type, envelope_id)

                # Slack can send payload as either a dict or a JSON-encoded string
                event_payload = payload.get("payload", {})
                if isinstance(event_payload, str):
                    try:
                        event_payload = json.loads(event_payload)
                    except json.JSONDecodeError:
                        event_payload = {}

                event = event_payload.get("event", {}) if isinstance(event_payload, dict) else {}
                event_type = event.get("type")
                channel_type = event.get("channel_type", "")
                subtype = event.get("subtype")

                logger.info(
                    "Slack event: event_type=%s channel=%s channel_type=%s user=%s bot_id=%s subtype=%s",
                    event_type,
                    event.get("channel"),
                    channel_type,
                    event.get("user"),
                    event.get("bot_id"),
                    subtype,
                )

                # Handle incoming slash command invocations
                if isinstance(event_payload, dict) and event_payload.get("type") == "slash_commands":
                    await self._handle_slash_command(event_payload)
                    continue

                # Handle regular messages and file_share subtypes; ignore bot messages and other subtypes
                is_handled_subtype = subtype in _HANDLED_SUBTYPES
                if (
                    event_type == "message"
                    and not event.get("bot_id")
                    and (subtype is None or is_handled_subtype)
                ):
                    is_group = channel_type not in ("im", "mpim", "app_home")
                    text = event.get("text", "")

                    # Collect any file attachments
                    attachments = await _collect_slack_attachments(
                        event.get("files") or [],
                        bot_token=token,
                    )

                    # Skip if neither text nor attachments were found
                    if not text and not attachments:
                        continue

                    # Placeholder when file arrives without text
                    if not text and attachments:
                        names = ", ".join(a["filename"] for a in attachments)
                        text = f"[File attachment: {names}]"

                    logger.info(
                        "Slack dispatching: channel=%s is_group=%s is_mention=%s text=%r attachments=%d",
                        event.get("channel"),
                        is_group,
                        "<@" in text,
                        text[:80],
                        len(attachments),
                    )
                    inbound = InboundMessage(
                        platform="slack",
                        platform_chat_id=event.get("channel", ""),
                        platform_user_id=event.get("user", ""),
                        platform_message_id=event.get("ts", ""),
                        content=text,
                        attachments=attachments if attachments else None,
                        is_group=is_group,
                        is_mention="<@" in text,
                    )
                    await self.dispatch(inbound)

    async def _handle_slash_command(self, payload: dict) -> None:
        """Dispatch an incoming Slack slash command as a regular inbound message.

        Slack delivers slash command invocations (e.g. ``/help``) as a
        ``slash_commands`` payload over Socket Mode.  We normalise these into an
        :class:`InboundMessage` so the agent pipeline handles them identically to
        plain text messages.
        """
        command = payload.get("command", "")        # e.g. "/help"
        text = payload.get("text", "").strip()      # arguments after the command
        channel_id = payload.get("channel_id", "")
        user_id = payload.get("user_id", "")
        username = payload.get("user_name", "")
        trigger_id = payload.get("trigger_id", "")

        # Build a natural-language content string from the slash command
        content = command if not text else f"{command} {text}"

        logger.info(
            "Slack slash command: command=%s text=%r channel=%s user=%s trigger_id=%s",
            command,
            text,
            channel_id,
            user_id,
            trigger_id,
        )

        inbound = InboundMessage(
            platform="slack",
            platform_chat_id=channel_id,
            platform_user_id=user_id,
            platform_username=username,
            platform_message_id=trigger_id,
            content=content,
            is_group=False,
            is_mention=False,
        )
        await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        token = self.config.token
        if not token:
            logger.warning("Slack bot token not configured, cannot send")
            return

        logger.info("Slack sending to channel=%s", message.platform_chat_id)
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
            if data.get("ok"):
                logger.info("Slack send OK to channel=%s", message.platform_chat_id)
            else:
                logger.error("Slack send failed: %s (channel=%s)", data.get("error"), message.platform_chat_id)


# ── Attachment helpers ───────────────────────────────────────────────────────

async def _collect_slack_attachments(files: list[dict], bot_token: str) -> list[dict]:
    """Download Slack file objects and return normalised attachment dicts.

    Each entry in ``files`` is a Slack file object with keys like
    ``name``, ``mimetype``, ``url_private_download``, etc.
    """
    result: list[dict] = []
    for file_obj in files:
        filename = file_obj.get("name") or file_obj.get("title") or "file"
        mime = file_obj.get("mimetype")
        url = file_obj.get("url_private_download") or file_obj.get("url_private")

        if not url:
            # Include metadata-only entry so the agent knows a file was sent
            result.append(build_attachment_dict(filename=filename, mime=mime, data=None))
            continue

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {bot_token}"},
                )
                resp.raise_for_status()
                data = resp.content
            att_dict = build_attachment_dict(filename=filename, mime=mime, data=data)
            # Transcribe audio/voice messages (e.g. M4A voice memos)
            if att_dict["category"] == "audio" and not att_dict.get("text_content"):
                transcription = await transcribe_audio_attachment(data, filename)
                if transcription:
                    att_dict["text_content"] = transcription
            result.append(att_dict)
        except Exception:
            logger.exception("Failed to download Slack file '%s'", filename)
            result.append(build_attachment_dict(filename=filename, mime=mime, data=None))

    return result
