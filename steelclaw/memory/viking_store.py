"""OpenViking server-backed context store for persistent semantic memory."""

from __future__ import annotations

import hashlib
import logging
import sys
from typing import Any

from steelclaw.settings import MemorySettings

logger = logging.getLogger("steelclaw.memory")

_openviking_available = False
try:
    from openviking import SyncHTTPClient  # type: ignore[import]
    _openviking_available = True
except ImportError:
    pass

# Keywords for simple heuristic category classification
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("profile",     ["i am ", "my name", "i'm ", "i work"]),
    ("preferences", ["i prefer", "i like", "i love", "i hate", "i enjoy", "i dislike"]),
    ("cases",       ["error", "fix", "problem", "bug", "issue", "crash", "exception", "fail"]),
    ("patterns",    ["always", "usually", "typically", "every time", "whenever"]),
    ("events",      []),  # catch-all
]

VALID_CATEGORIES = frozenset({"profile", "preferences", "entities", "events", "cases", "patterns"})


def classify_category(text: str) -> str:
    """Return an OpenViking memory category based on keyword heuristics."""
    lower = text.lower()
    for category, keywords in _CATEGORY_RULES:
        if not keywords:
            return category  # catch-all
        if any(kw in lower for kw in keywords):
            return category
    return "events"


class VikingStore:
    """Persistent context store backed by an OpenViking server.

    Implements the same interface as VectorStore so it can be used as a
    drop-in replacement in MemoryIngestor and MemoryRetriever.

    Degrades gracefully to a no-op when:
    - openviking package is not installed
    - OpenViking server is unreachable
    - memory.enabled is False
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._client: Any = None
        self._session_id: str | None = None

        if not settings.enabled:
            logger.info("Memory system disabled via config")
            return

        if not _openviking_available:
            logger.warning(
                "openviking not installed — memory system disabled. "
                "Install with: pip install steelclaw[openviking]"
            )
            return

        try:
            client = SyncHTTPClient(
                url=settings.openviking_server_url,
                timeout=30.0,
            )
            # Create or get session for this workspace
            self._session_id = f"steelclaw-{settings.openviking_workspace}"

            # Test connection - check if server is healthy
            try:
                is_healthy = client.is_healthy()
            except Exception:
                is_healthy = False

            if not is_healthy:
                logger.warning(
                    "OpenViking server not healthy at %s — memory system disabled",
                    settings.openviking_server_url,
                )
                return

            self._client = client
            logger.info(
                "OpenViking connected to %s (workspace=%s)",
                settings.openviking_server_url,
                settings.openviking_workspace,
            )
        except Exception as exc:
            logger.warning(
                "OpenViking connection failed (%s) — memory disabled", exc
            )
            self._client = None
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        doc_id: str | None = None,
        namespace: str | None = None,
    ) -> str | None:
        """Add a document to OpenViking. Returns the document ID."""
        if self._client is None:
            return None

        doc_id = doc_id or self._content_hash(text)

        # Add message to the session
        # OpenViking expects session_id, role, content
        try:
            result = self._client.add_message(
                session_id=self._session_id,
                role="assistant",  # Store as assistant message
                content=text,
            )
            logger.debug("Added memory to OpenViking: %s", doc_id)
            return doc_id
        except Exception as exc:
            logger.error("OpenViking add error: %s", exc)
            return None

    def query(
        self,
        text: str,
        n_results: int = 5,
        namespace: str | None = None,
        where: dict | None = None,
    ) -> list[dict]:
        """Query for relevant documents. Returns [{id, document, metadata, distance}]."""
        if self._client is None:
            return []

        try:
            results = self._client.search(
                query=text,
                session_id=self._session_id,
                limit=n_results,
            )
        except Exception as exc:
            logger.error("OpenViking search error: %s", exc)
            return []

        docs = []
        for item in results or []:
            # OpenViking returns results in a different format
            # Convert to ChromaDB-like format
            doc_id = item.get("id", item.get("uri", ""))
            content = item.get("content", item.get("text", ""))
            score = item.get("score", item.get("relevance", 1.0))
            docs.append({
                "id": doc_id,
                "document": content,
                "metadata": item.get("metadata", {}),
                "distance": 1.0 - score,  # similarity → distance (matches ChromaDB convention)
            })
        return docs

    def delete(self, ids: list[str], namespace: str | None = None) -> None:
        """Delete documents by ID."""
        if self._client is None:
            return
        # OpenViking doesn't have a direct delete by ID
        # Would need to use session management
        logger.warning("OpenViking delete not fully implemented")

    def count(self, namespace: str | None = None) -> int:
        """Return total document count."""
        if self._client is None:
            return 0
        try:
            # Get session context and count messages
            status = self._client.get_status()
            return status.get("total_messages", 0)
        except Exception as exc:
            logger.error("OpenViking count error: %s", exc)
            return 0

    def clear(self, namespace: str | None = None) -> None:
        """Clear all documents from the OpenViking workspace."""
        if self._client is None:
            return
        try:
            self._client.delete_session(self._session_id)
            self._client.create_session(self._session_id)
            logger.info(
                "Cleared OpenViking workspace: %s",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking clear error: %s", exc)

    def commit_session(self) -> None:
        """Commit session for long-term memory categorisation (OpenViking-specific)."""
        if self._client is None:
            return
        try:
            self._client.commit_session(self._session_id)
            logger.debug(
                "OpenViking session committed (workspace=%s)",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking commit error: %s", exc)