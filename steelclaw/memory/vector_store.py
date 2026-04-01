"""ChromaDB vector store wrapper for persistent semantic memory."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from steelclaw.settings import MemorySettings

logger = logging.getLogger("steelclaw.memory")

_chromadb_available = False
try:
    import chromadb  # noqa: F401
    _chromadb_available = True
except ImportError:
    pass


class VectorStore:
    """Persistent vector store backed by ChromaDB.

    Degrades gracefully to a no-op if ChromaDB is not installed.
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._client = None
        self._collections: dict[str, object] = {}

        if not settings.enabled:
            logger.info("Memory system disabled via config")
            return

        if not _chromadb_available:
            logger.warning(
                "ChromaDB not installed — memory system disabled. "
                "Install with: pip install steelclaw[memory]"
            )
            return

        persist_dir = Path(settings.chromadb_path).expanduser()
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info("ChromaDB initialised at %s", persist_dir)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _get_collection(self, namespace: str | None = None):
        """Get or create a ChromaDB collection for the given namespace."""
        if self._client is None:
            return None
        name = namespace or self._settings.collection_name
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

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
        """Add a document to the vector store. Returns the document ID."""
        collection = self._get_collection(namespace)
        if collection is None:
            return None

        doc_id = doc_id or self._content_hash(text)
        meta = metadata or {}
        meta["content_hash"] = self._content_hash(text)

        collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )
        return doc_id

    def query(
        self,
        text: str,
        n_results: int = 5,
        namespace: str | None = None,
        where: dict | None = None,
    ) -> list[dict]:
        """Query for relevant documents. Returns list of {id, document, metadata, distance}."""
        collection = self._get_collection(namespace)
        if collection is None:
            return []

        kwargs = {"query_texts": [text], "n_results": n_results}
        if where:
            kwargs["where"] = where

        try:
            results = collection.query(**kwargs)
        except Exception as e:
            logger.error("ChromaDB query error: %s", e)
            return []

        docs = []
        if results and results.get("ids"):
            for i, doc_id in enumerate(results["ids"][0]):
                docs.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                })
        return docs

    def delete(self, ids: list[str], namespace: str | None = None) -> None:
        """Delete documents by ID."""
        collection = self._get_collection(namespace)
        if collection is None:
            return
        collection.delete(ids=ids)

    def count(self, namespace: str | None = None) -> int:
        """Return total number of documents in the collection."""
        collection = self._get_collection(namespace)
        if collection is None:
            return 0
        return collection.count()

    def clear(self, namespace: str | None = None) -> None:
        """Delete the entire collection and recreate it."""
        if self._client is None:
            return
        name = namespace or self._settings.collection_name
        try:
            self._client.delete_collection(name)
        except Exception:
            pass
        self._collections.pop(name, None)
        logger.info("Cleared memory collection: %s", name)
