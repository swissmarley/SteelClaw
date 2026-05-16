"""OpenViking server-backed context store for persistent semantic memory.

Uses httpx for HTTP communication with the OpenViking server rather than
the openviking SDK's SyncHTTPClient, which creates its own event loop and
conflicts with SteelClaw's asyncio loop.

All endpoints use the /api/v1/ prefix per the OpenViking 0.3.x REST API.
Responses are wrapped in {"status": "ok", "result": {...}}.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from steelclaw.settings import MemorySettings

logger = logging.getLogger("steelclaw.memory")

_httpx_available = False
try:
    import httpx
    _httpx_available = True
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

    Uses raw HTTP calls via httpx instead of the OpenViking SDK client to
    avoid event-loop conflicts (the SDK's SyncHTTPClient creates its own
    event loop which clashes with SteelClaw's running asyncio loop).

    All endpoints target the /api/v1/ namespace (OpenViking 0.3.x).

    Degrades gracefully to a no-op when:
    - httpx is not installed
    - OpenViking server is unreachable
    - memory.enabled is False
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._base_url: str = settings.openviking_server_url.rstrip("/")
        self._session_id: str = f"steelclaw-{settings.openviking_workspace}"
        self._http: httpx.Client | None = None

        if not settings.enabled:
            logger.info("Memory system disabled via config")
            return

        if not _httpx_available:
            logger.warning("httpx not installed — memory system disabled")
            return

        # Test connection with retries
        import time
        is_healthy = False
        for attempt in range(5):
            try:
                resp = httpx.get(f"{self._base_url}/health", timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("healthy") or data.get("status") == "ok":
                        is_healthy = True
                        break
            except Exception:
                pass
            time.sleep(0.5)

        if not is_healthy:
            logger.warning(
                "OpenViking server not healthy at %s — memory system disabled",
                self._base_url,
            )
            return

        self._http = httpx.Client(base_url=self._base_url, timeout=30.0)

        # Ensure our session exists
        self._ensure_session()

        logger.info(
            "OpenViking connected to %s (workspace=%s, session=%s)",
            self._base_url,
            settings.openviking_workspace,
            self._session_id,
        )

    def _ensure_session(self) -> None:
        """Create the session if it doesn't exist yet."""
        if self._http is None:
            return
        try:
            # Check if session exists
            resp = self._http.get(f"/api/v1/sessions/{self._session_id}")
            if resp.status_code == 404:
                # Create it
                self._http.post(
                    "/api/v1/sessions",
                    json={"session_id": self._session_id},
                )
                logger.debug("Created OpenViking session: %s", self._session_id)
        except Exception as exc:
            logger.debug("Session check/create: %s", exc)

    @property
    def available(self) -> bool:
        return self._http is not None

    def _reconnect_if_needed(self) -> bool:
        """Try to reconnect to OpenViking if the connection was lost. Returns True if connected."""
        if self._http is not None:
            return True
        try:
            resp = httpx.get(f"{self._base_url}/health", timeout=2.0)
            if resp.status_code == 200:
                self._http = httpx.Client(base_url=self._base_url, timeout=30.0)
                self._ensure_session()
                logger.info("OpenViking reconnected to %s", self._base_url)
                return True
        except Exception:
            pass
        return False

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
        """Add a document to OpenViking via session message. Returns the document ID."""
        if self._http is None and not self._reconnect_if_needed():
            return None

        doc_id = doc_id or self._content_hash(text)

        try:
            resp = self._http.post(
                f"/api/v1/sessions/{self._session_id}/messages",
                json={
                    "role": "assistant",
                    "content": text,
                },
            )
            resp.raise_for_status()
            logger.debug("Added memory to OpenViking: %s", doc_id)
            return doc_id
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            logger.warning("OpenViking connection lost — will retry on next request")
            self._http = None
            return None
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
        if self._http is None and not self._reconnect_if_needed():
            return []

        try:
            resp = self._http.post(
                "/api/v1/search/find",
                json={
                    "query": text,
                    "limit": n_results,
                },
            )
            resp.raise_for_status()
            envelope = resp.json()
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            logger.warning("OpenViking connection lost — will retry on next request")
            self._http = None
            return []
        except Exception as exc:
            logger.error("OpenViking search error: %s", exc)
            return []

        # OpenViking wraps results in {"status": "ok", "result": {...}}
        data = envelope.get("result", envelope)

        docs = []
        for key in ("memories", "resources"):
            for item in data.get(key, []):
                doc_id = item.get("uri", "")
                content = item.get("abstract", "") or item.get("overview", "") or ""
                score = item.get("score", 0.0)
                category = item.get("category", "")
                docs.append({
                    "id": doc_id,
                    "document": content,
                    "metadata": {"category": category, "uri": doc_id},
                    "distance": 1.0 - score,
                })

        return docs[:n_results]

    def delete(self, ids: list[str], namespace: str | None = None) -> None:
        """Delete documents by ID."""
        if self._http is None:
            return
        # OpenViking doesn't have a direct delete-by-ID endpoint
        logger.warning("OpenViking delete not fully implemented")

    def count(self, namespace: str | None = None) -> int:
        """Return total memory count from OpenViking stats."""
        if self._http is None and not self._reconnect_if_needed():
            return 0
        try:
            resp = self._http.get("/api/v1/stats/memories")
            resp.raise_for_status()
            envelope = resp.json()
            data = envelope.get("result", envelope)
            return data.get("total_memories", 0)
        except Exception as exc:
            logger.error("OpenViking count error: %s", exc)
            return 0

    def clear(self, namespace: str | None = None) -> None:
        """Clear all documents by deleting and recreating the session."""
        if self._http is None:
            return
        try:
            self._http.delete(f"/api/v1/sessions/{self._session_id}")
            self._http.post(
                "/api/v1/sessions",
                json={"session_id": self._session_id},
            )
            logger.info(
                "Cleared OpenViking workspace: %s",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking clear error: %s", exc)

    def commit_session(self) -> None:
        """Commit session for long-term memory categorisation (OpenViking-specific)."""
        if self._http is None:
            return
        try:
            resp = self._http.post(
                f"/api/v1/sessions/{self._session_id}/commit",
            )
            resp.raise_for_status()
            logger.debug(
                "OpenViking session committed (workspace=%s)",
                self._settings.openviking_workspace,
            )
        except Exception as exc:
            logger.error("OpenViking commit error: %s", exc)
