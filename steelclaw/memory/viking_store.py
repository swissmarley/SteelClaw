"""OpenViking server-backed context store for persistent semantic memory."""

from __future__ import annotations

import hashlib
import logging
import sys
from typing import Any

from steelclaw.settings import MemorySettings

logger = logging.getLogger("steelclaw.memory")

_openviking_available = False
if sys.version_info >= (3, 10):
    try:
        import openviking  # noqa: F401
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
    - Python < 3.10
    - OpenViking server is unreachable
    - memory.enabled is False
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._client: Any = None
        self._session: Any = None

        if not settings.enabled:
            logger.info("Memory system disabled via config")
            return

        if sys.version_info < (3, 10):
            logger.warning(
                "OpenViking requires Python 3.10+ — memory system disabled "
                "(current: %d.%d)",
                sys.version_info.major,
                sys.version_info.minor,
            )
            return

        if not _openviking_available:
            logger.warning(
                "openviking not installed — memory system disabled. "
                "Install with: pip install steelclaw[openviking]"
            )
            return

        try:
            from openviking import Client  # type: ignore[import]
            self._client = Client(base_url=settings.openviking_server_url)
            self._session = self._client.session(settings.openviking_workspace)
            logger.info(
                "OpenViking initialised at %s (workspace=%s)",
                settings.openviking_server_url,
                settings.openviking_workspace,
            )
        except Exception as exc:
            logger.warning(
                "OpenViking connection failed (%s) — memory disabled", exc
            )

    @property
    def available(self) -> bool:
        return self._session is not None

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    @staticmethod
    def _make_uri(category: str, doc_id: str) -> str:
        return f"viking://memory/{category}/{doc_id}"

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        doc_id: str | None = None,
        namespace: str | None = None,
    ) -> str | None:
        """Add a document to OpenViking. Returns the document ID."""
        if self._session is None:
            return None

        doc_id = doc_id or self._content_hash(text)
        category = classify_category(text)
        meta = {**(metadata or {})}
        meta["content_hash"] = self._content_hash(text)
        if namespace:
            meta["namespace"] = namespace

        try:
            self._session.add(
                uri=self._make_uri(category, doc_id),
                content=text,
                metadata=meta,
            )
        except Exception as exc:
            logger.error("OpenViking add error: %s", exc)
            return None

        return doc_id

    def query(
        self,
        text: str,
        n_results: int = 5,
        namespace: str | None = None,
        where: dict | None = None,
    ) -> list[dict]:
        """Query for relevant documents. Returns [{id, document, metadata, distance}]."""
        if self._session is None:
            return []

        tier = self._settings.openviking_context_tier
        try:
            raw = self._session.search(text, n=n_results, tier=tier)
        except Exception as exc:
            logger.error("OpenViking search error: %s", exc)
            return []

        docs = []
        for item in raw or []:
            uri = item.get("uri", "")
            doc_id = uri.split("/")[-1] if uri else ""
            score = item.get("score", 0.0)
            docs.append({
                "id": doc_id,
                "document": item.get("content", ""),
                "metadata": item.get("metadata", {}),
                "distance": 1.0 - score,  # similarity → distance (matches ChromaDB convention)
            })
        return docs

    def delete(self, ids: list[str], namespace: str | None = None) -> None:
        """Delete documents by ID across all known categories."""
        if self._session is None:
            return
        for doc_id in ids:
            for category in VALID_CATEGORIES:
                try:
                    self._session.delete(uri=self._make_uri(category, doc_id))
                except Exception:
                    pass  # not present in this category — expected

    def count(self, namespace: str | None = None) -> int:
        """Return total document count."""
        if self._session is None:
            return 0
        try:
            return self._session.count()
        except Exception as exc:
            logger.error("OpenViking count error: %s", exc)
            return 0

    def clear(self, namespace: str | None = None) -> None:
        """Clear all documents from the OpenViking workspace."""
        if self._session is None:
            return
        try:
            self._session.clear()
            logger.info(
                "Cleared OpenViking workspace: %s",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking clear error: %s", exc)

    def commit_session(self) -> None:
        """Commit session for long-term memory categorisation (OpenViking-specific).

        Triggers OpenViking's automatic compression and 6-category persistent
        memory extraction (profile, preferences, entities, events, cases, patterns).
        """
        if self._session is None:
            return
        try:
            self._session.commit()
            logger.debug(
                "OpenViking session committed (workspace=%s)",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking commit error: %s", exc)
