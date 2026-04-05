"""Conversation context builder — loads history from DB and builds LLM prompts."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import Message as DBMessage, Session as DBSession
from steelclaw.settings import LLMSettings

logger = logging.getLogger("steelclaw.llm.context")


class ContextBuilder:
    """Builds a message list suitable for LLM completion from DB history."""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    async def build(
        self,
        session: DBSession,
        db: AsyncSession,
        system_prompt: str | None = None,
        skill_context: str | None = None,
        memory_context: str | None = None,
        persona_prompt: str | None = None,
        current_message: str | None = None,
        attachments: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Build the full message list for an LLM call.

        Order: persona → system → memory context → skill context → history → current message.
        """
        messages: list[dict[str, Any]] = []

        # System prompt (with persona, memory, and skill context appended)
        parts = []
        if persona_prompt:
            parts.append(persona_prompt)
        parts.append(system_prompt or self._settings.system_prompt)
        if memory_context:
            parts.append(memory_context)
        if skill_context:
            parts.append(skill_context)
        messages.append({"role": "system", "content": "\n\n".join(parts)})

        # Load history from unified session (cross-platform DM collapse)
        history = await self._load_history(session, db)
        messages.extend(history)

        # Current user message with optional multimodal attachments
        if current_message or attachments:
            messages.append(self._build_user_message(current_message or "", attachments))

        return messages

    def _build_user_message(
        self, text: str, attachments: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Build a user message, optionally with multimodal content (images, docs)."""
        if not attachments:
            return {"role": "user", "content": text}

        # Build multimodal content array for the LLM
        content_parts: list[dict[str, Any]] = []

        for att in attachments:
            category = att.get("category", "unknown")
            filename = att.get("filename", "file")

            if category == "image" and att.get("base64"):
                # Send images as base64 inline (Claude/OpenAI vision)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{att['mime']};base64,{att['base64']}",
                    },
                })
            elif category in ("document", "audio"):
                # Send extracted text as a text block
                file_text = att.get("text_content", "")
                if file_text:
                    content_parts.append({
                        "type": "text",
                        "text": f"[Attached file: {filename}]\n{file_text}",
                    })
                else:
                    content_parts.append({
                        "type": "text",
                        "text": f"[Attached file: {filename} — content could not be extracted]",
                    })

        # Add the user's text message
        if text:
            content_parts.append({"type": "text", "text": text})

        return {"role": "user", "content": content_parts}

    async def _load_history(
        self,
        session: DBSession,
        db: AsyncSession,
    ) -> list[dict[str, str]]:
        """Load recent messages from all sessions sharing the unified_session_id."""
        unified_id = session.unified_session_id or session.id
        limit = self._settings.max_context_messages

        # Find all session IDs in this unified group
        session_stmt = select(DBSession.id).where(
            DBSession.unified_session_id == unified_id
        )
        session_result = await db.execute(session_stmt)
        session_ids = [row[0] for row in session_result.all()]

        if not session_ids:
            session_ids = [session.id]

        # Load messages ordered by creation time, most recent first, then reverse
        msg_stmt = (
            select(DBMessage)
            .where(DBMessage.session_id.in_(session_ids))
            .where(DBMessage.role.in_(["user", "assistant"]))
            .order_by(DBMessage.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(msg_stmt)
        db_messages = list(reversed(result.scalars().all()))

        return [
            {"role": msg.role, "content": msg.content}
            for msg in db_messages
        ]

    def build_tool_result_message(self, tool_call_id: str, result: str) -> dict[str, Any]:
        """Build a tool result message to feed back to the LLM."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def build_assistant_tool_call_message(self, content: str | None, tool_calls: list) -> dict:
        """Build the assistant message that contains tool calls."""
        # Use None (not "") for content when there are tool calls — required by OpenAI spec
        # and needed for correct LiteLLM transformation to Anthropic/other provider formats.
        msg: Dict[str, Any] = {"role": "assistant", "content": content if content else None}
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": __import__("json").dumps(tc.arguments),
                },
            }
            for tc in tool_calls
        ]
        return msg
