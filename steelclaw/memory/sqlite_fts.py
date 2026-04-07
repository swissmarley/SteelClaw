"""SQLite FTS5 keyword-search memory layer.

Provides fast full-text search over agent memories using SQLite's built-in
FTS5 extension with Porter stemming.  This complements the vector-based
semantic memory (ChromaDB / OpenViking) with exact-keyword and stemmed lookup.

The store also supports "memory nudge" prompts: a short formatted string of
recent relevant memories injected into the agent's system prompt to ground
responses in past context.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("steelclaw.memory.fts")

# DDL executed once on first connection
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fts_meta (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id  TEXT    NOT NULL DEFAULT '',
    session_id TEXT   NOT NULL DEFAULT '',
    source_type TEXT  NOT NULL DEFAULT 'message',
    tags      TEXT    NOT NULL DEFAULT '',
    created_at TEXT   NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    tags,
    source_type,
    agent_id      UNINDEXED,
    session_id    UNINDEXED,
    rowid=id,
    tokenize='porter ascii'
);
"""


class FTSMemoryStore:
    """Async SQLite FTS5 memory store."""

    def __init__(self, db_path: str) -> None:
        self._db_path = str(Path(db_path).expanduser().resolve())
        self._db = None  # aiosqlite connection

    async def init(self) -> None:
        """Create the FTS5 table if it doesn't exist and open the connection."""
        try:
            import aiosqlite
        except ImportError:
            logger.warning(
                "aiosqlite not available — FTS memory disabled. "
                "Install with: pip install aiosqlite"
            )
            return

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA_SQL)
        await self._db.commit()
        logger.info("FTS memory store initialised at %s", self._db_path)

    async def store(
        self,
        content: str,
        tags: list[str] | None = None,
        source_type: str = "message",
        agent_id: str = "",
        session_id: str = "",
    ) -> None:
        """Insert a memory entry into the FTS index."""
        if self._db is None:
            return
        tags_str = " ".join(tags or [])
        try:
            await self._db.execute(
                """INSERT INTO memory_fts(content, tags, source_type, agent_id, session_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (content, tags_str, source_type, agent_id, session_id),
            )
            await self._db.commit()
        except Exception as exc:
            logger.error("FTS store error: %s", exc)

    async def search(
        self,
        query: str,
        limit: int = 10,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text search returning matching memory entries.

        Returns a list of dicts with keys: content, tags, source_type,
        agent_id, session_id, rank (lower = more relevant).
        """
        if self._db is None:
            return []

        # Escape special FTS5 characters in the query
        safe_query = _escape_fts5(query)
        if not safe_query:
            return []

        try:
            if agent_id:
                cursor = await self._db.execute(
                    """SELECT content, tags, source_type, agent_id, session_id, rank
                       FROM memory_fts
                       WHERE memory_fts MATCH ? AND agent_id = ?
                       ORDER BY rank
                       LIMIT ?""",
                    (safe_query, agent_id, limit),
                )
            else:
                cursor = await self._db.execute(
                    """SELECT content, tags, source_type, agent_id, session_id, rank
                       FROM memory_fts
                       WHERE memory_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (safe_query, limit),
                )
            rows = await cursor.fetchall()
            return [
                {
                    "content": r[0],
                    "tags": r[1],
                    "source_type": r[2],
                    "agent_id": r[3],
                    "session_id": r[4],
                    "rank": r[5],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("FTS search error (query=%r): %s", query[:80], exc)
            return []

    async def recent(
        self,
        agent_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the most recently stored entries for *agent_id*."""
        if self._db is None:
            return []
        try:
            cursor = await self._db.execute(
                """SELECT content, tags, source_type, agent_id, session_id
                   FROM memory_fts
                   WHERE agent_id = ?
                   ORDER BY rowid DESC
                   LIMIT ?""",
                (agent_id, limit),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "content": r[0],
                    "tags": r[1],
                    "source_type": r[2],
                    "agent_id": r[3],
                    "session_id": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("FTS recent error: %s", exc)
            return []

    async def nudge_prompt(
        self,
        agent_id: str,
        limit: int | None = None,
    ) -> str:
        """Return a formatted memory-nudge string for system prompt injection.

        Pulls the *limit* most recent memories for *agent_id* and formats them
        as a short reminder block.  Returns an empty string when nothing is found
        or the store is unavailable.
        """
        nudge_limit = limit or 3
        entries = await self.recent(agent_id, nudge_limit)
        if not entries:
            return ""

        lines = ["[Memory hints from previous sessions:]"]
        for entry in entries:
            snippet = entry["content"][:200].replace("\n", " ")
            src = entry.get("source_type", "")
            tag = entry.get("tags", "").strip()
            label = f"[{src}]" if src else ""
            if tag:
                label = f"{label}[{tag}]"
            lines.append(f"- {label} {snippet}")

        return "\n".join(lines)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None


def _escape_fts5(query: str) -> str:
    """Escape a user query string for safe use in FTS5 MATCH expressions.

    Removes characters that have special meaning in FTS5 syntax to prevent
    query injection and parse errors.
    """
    # Remove FTS5 special characters: " ( ) * ^ : -
    cleaned = "".join(c for c in query if c not in '"()*^:-')
    # Collapse whitespace and strip
    return " ".join(cleaned.split())
