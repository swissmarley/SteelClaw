"""iMessage connector — macOS AppleScript bridge."""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from pathlib import Path

from steelclaw.gateway.base import BaseConnector
from steelclaw.schemas.messages import InboundMessage, OutboundMessage

logger = logging.getLogger("steelclaw.gateway.imessage")


class IMessageConnector(BaseConnector):
    """iMessage connector using macOS AppleScript bridge.

    Config requires:
    - extra.watch_interval: Polling interval in seconds (default: 5)

    Note: Only works on macOS. Requires Full Disk Access for the terminal
    application to read the Messages database.
    """

    platform_name = "imessage"

    def __init__(self, config, handler) -> None:
        super().__init__(config, handler)
        self._last_rowid: int = 0
        self._db_path = Path.home() / "Library" / "Messages" / "chat.db"

    async def _run(self) -> None:
        if platform.system() != "Darwin":
            logger.error("iMessage connector only works on macOS")
            return

        if not self._db_path.exists():
            logger.error("iMessage database not found at %s", self._db_path)
            return

        interval = int(self.config.extra.get("watch_interval", 5))
        logger.info("iMessage connector started (polling every %ds)", interval)

        # Get the latest message ROWID to avoid processing old messages
        self._last_rowid = await self._get_latest_rowid()

        while True:
            try:
                await self._poll_new_messages()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("iMessage polling error")
                await asyncio.sleep(interval)

    async def _get_latest_rowid(self) -> int:
        """Get the most recent message ROWID from the chat.db."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["sqlite3", str(self._db_path), "SELECT MAX(ROWID) FROM message;"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        except Exception:
            pass
        return 0

    async def _poll_new_messages(self) -> None:
        """Poll for new messages since last ROWID."""
        query = (
            "SELECT message.ROWID, message.text, message.is_from_me, "
            "message.handle_id, handle.id as sender, "
            "message.cache_roomnames "
            "FROM message "
            "LEFT JOIN handle ON message.handle_id = handle.ROWID "
            f"WHERE message.ROWID > {self._last_rowid} "
            "AND message.text IS NOT NULL "
            "ORDER BY message.ROWID;"
        )

        result = await asyncio.to_thread(
            subprocess.run,
            ["sqlite3", "-separator", "|", str(self._db_path), query],
            capture_output=True, text=True, timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return

        for line in result.stdout.strip().split("\n"):
            parts = line.split("|", 5)
            if len(parts) < 5:
                continue

            rowid, text, is_from_me, handle_id, sender = parts[0], parts[1], parts[2], parts[3], parts[4]
            room_name = parts[5] if len(parts) > 5 else ""

            self._last_rowid = max(self._last_rowid, int(rowid))

            # Skip our own messages
            if is_from_me == "1":
                continue

            inbound = InboundMessage(
                platform="imessage",
                platform_chat_id=room_name or sender,
                platform_user_id=sender,
                platform_message_id=rowid,
                platform_username=sender,
                content=text,
                is_group=bool(room_name),
                is_mention=False,
            )
            await self.dispatch(inbound)

    async def send(self, message: OutboundMessage) -> None:
        if platform.system() != "Darwin":
            logger.warning("iMessage send only works on macOS")
            return

        recipient = message.platform_chat_id
        text = message.content.replace('"', '\\"').replace("'", "'\\''")

        # Use AppleScript to send message
        script = (
            f'tell application "Messages"\n'
            f'    set targetService to 1st service whose service type = iMessage\n'
            f'    set targetBuddy to buddy "{recipient}" of targetService\n'
            f'    send "{text}" to targetBuddy\n'
            f'end tell'
        )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.error("iMessage send failed: %s", result.stderr[:200])
        except Exception:
            logger.exception("iMessage AppleScript error")
