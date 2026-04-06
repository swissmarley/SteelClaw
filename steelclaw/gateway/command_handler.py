"""Slash command dispatcher — handles bot commands directly without routing to the LLM.

Commands that are handled here return a formatted string immediately.
Commands that return ``None`` fall through to the normal agent/LLM pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from steelclaw.gateway.commands import SLASH_COMMANDS

logger = logging.getLogger("steelclaw.gateway.command_handler")

# ── Help text ────────────────────────────────────────────────────────────────

_HELP_HEADER = "**SteelClaw Commands**\n"
_HELP_FOOTER = "\nSend any other message to chat with the AI assistant."

# Commands visible to messenger-platform users
_MESSENGER_COMMANDS: list[tuple[str, str]] = [
    ("/help",    "Show this command list"),
    ("/status",  "Show current session and bot status"),
    ("/run",     "Execute a task  — e.g. `/run summarise the news`"),
    ("/stop",    "End the current session"),
    ("/memory",  "Memory actions: `status` · `clear`"),
    ("/config",  "Show active configuration"),
    ("/history", "Show recent conversation history (last 10 messages)"),
    ("/new",     "Start a fresh conversation"),
]


def _help_text() -> str:
    lines = [_HELP_HEADER]
    for cmd, desc in _MESSENGER_COMMANDS:
        lines.append(f"• `{cmd}` — {desc}")
    lines.append(_HELP_FOOTER)
    return "\n".join(lines)


# ── Main dispatcher ──────────────────────────────────────────────────────────


async def dispatch_command(
    content: str,
    *,
    session=None,
    db=None,
    settings=None,
) -> str | None:
    """Attempt to handle *content* as a slash command.

    Returns a response string if the command is handled here, or ``None``
    if the message should fall through to the normal LLM agent pipeline.
    Unrecognised ``/`` commands also return ``None`` so the agent can
    respond naturally (e.g. "I don't know that command, but…").
    """
    stripped = content.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/help", "/start"):
        return _help_text()

    if cmd == "/status":
        return _build_status(session)

    if cmd in ("/stop", "/quit", "/exit"):
        return await _handle_stop(session, db)

    if cmd == "/memory":
        return await _handle_memory(args, session, db)

    if cmd == "/config":
        return _handle_config(settings)

    if cmd == "/history":
        return await _handle_history(session, db)

    if cmd == "/new":
        return await _handle_new(session, db)

    # /run — forward to the LLM as a task instruction
    if cmd == "/run":
        return None

    # Any other /command — let the LLM handle it naturally
    return None


# ── Command implementations ──────────────────────────────────────────────────


def _build_status(session) -> str:
    lines = ["**SteelClaw Status**", "✓ Online"]
    if session is not None:
        lines.append(f"\nSession ID: `{session.id[:8]}…`")
        lines.append(f"Platform:   {session.platform}")
        lines.append(f"Status:     {session.status}")
        if hasattr(session, "last_activity_at") and session.last_activity_at:
            try:
                last = session.last_activity_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                ago = datetime.now(timezone.utc) - last
                total_secs = int(ago.total_seconds())
                mins, secs = divmod(total_secs, 60)
                hours, mins = divmod(mins, 60)
                if hours:
                    age = f"{hours}h {mins}m ago"
                elif mins:
                    age = f"{mins}m {secs}s ago"
                else:
                    age = f"{secs}s ago"
                lines.append(f"Last active: {age}")
            except Exception:
                pass
    return "\n".join(lines)


async def _handle_stop(session, db) -> str:
    if session is not None and db is not None:
        try:
            session.status = "closed"
            if hasattr(session, "updated_at"):
                session.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return (
                "Session ended. ✓\n"
                "Send any message to start a new conversation."
            )
        except Exception as exc:
            logger.warning("Failed to close session %s: %s", getattr(session, "id", "?"), exc)
    return "Goodbye! Send a message to start a new session."


async def _handle_memory(args: str, session, db) -> str:
    action = args.lower().strip() if args else "status"

    if action == "status":
        return await _memory_status(session, db)

    if action == "clear":
        return await _memory_clear(session, db)

    if action.startswith("search "):
        query = args[len("search "):].strip()
        return f"Memory search is not available via chat commands yet. Query: `{query}`"

    return (
        f"Unknown memory action: `{args}`.\n"
        "Available: `/memory status` · `/memory clear`"
    )


async def _memory_status(session, db) -> str:
    if session is None or db is None:
        return "Memory: no active session."
    try:
        from sqlalchemy import func, select
        from steelclaw.db.models import Message as DBMessage

        result = await db.execute(
            select(func.count(DBMessage.id)).where(
                DBMessage.session_id == session.id
            )
        )
        count = result.scalar() or 0
        user_result = await db.execute(
            select(func.count(DBMessage.id)).where(
                DBMessage.session_id == session.id,
                DBMessage.role == "user",
            )
        )
        user_count = user_result.scalar() or 0
        return (
            f"**Memory Status**\n"
            f"Session messages: {count} total ({user_count} from you)\n"
            f"Use `/memory clear` to reset conversation history."
        )
    except Exception as exc:
        logger.warning("Memory status query failed: %s", exc)
        return "Memory status unavailable."


async def _memory_clear(session, db) -> str:
    if session is None or db is None:
        return "No active session to clear."
    try:
        from sqlalchemy import delete
        from steelclaw.db.models import Message as DBMessage

        await db.execute(
            delete(DBMessage).where(DBMessage.session_id == session.id)
        )
        await db.commit()
        return (
            "Conversation history cleared. ✓\n"
            "The assistant no longer has context from previous messages."
        )
    except Exception as exc:
        logger.warning("Memory clear failed for session %s: %s", getattr(session, "id", "?"), exc)
        return f"Failed to clear memory: {exc}"


async def _handle_history(session, db) -> str:
    if session is None or db is None:
        return "No conversation history available."
    try:
        from sqlalchemy import select
        from steelclaw.db.models import Message as DBMessage

        result = await db.execute(
            select(DBMessage)
            .where(DBMessage.session_id == session.id)
            .order_by(DBMessage.id.desc())
            .limit(10)
        )
        msgs = list(reversed(result.scalars().all()))
        if not msgs:
            return "No messages in current session yet."
        lines = ["**Last 10 Messages**"]
        for m in msgs:
            role = "You" if m.role == "user" else "SteelClaw"
            preview = (m.content or "")[:120].replace("\n", " ")
            if len(m.content or "") > 120:
                preview += "…"
            lines.append(f"**{role}:** {preview}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("History query failed: %s", exc)
        return "Could not retrieve history."


async def _handle_new(session, db) -> str:
    """Mark the current session as closed so the next message opens a fresh one."""
    if session is not None and db is not None:
        try:
            session.status = "closed"
            if hasattr(session, "updated_at"):
                session.updated_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            logger.warning("Could not close session for /new: %s", exc)
    return (
        "Fresh conversation started. ✓\n"
        "Send your next message to begin with a clean context."
    )


def _handle_config(settings) -> str:
    lines = ["**Active Configuration**"]
    if settings is None:
        lines.append("(settings not available)")
        return "\n".join(lines)
    try:
        if hasattr(settings, "mention_keywords") and settings.mention_keywords:
            lines.append(f"Mention keywords: {', '.join(settings.mention_keywords)}")
        if hasattr(settings, "dm_allowlist_enabled"):
            lines.append(f"DM allowlist: {settings.dm_allowlist_enabled}")
    except Exception:
        pass
    if len(lines) == 1:
        lines.append("Configuration loaded (no public fields to display).")
    return "\n".join(lines)
