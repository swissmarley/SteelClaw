"""Memory ingestion — stores conversation exchanges as vector embeddings."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import MemoryEntry
from steelclaw.memory.vector_store import VectorStore

logger = logging.getLogger("steelclaw.memory")


class MemoryIngestor:
    """Ingests message pairs into the vector store for later retrieval."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._store = vector_store

    async def ingest_exchange(
        self,
        user_message: str,
        assistant_message: str,
        session_id: str,
        agent_id: str | None = None,
        namespace: str | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """Store a user/assistant exchange as a searchable memory."""
        if not self._store.available:
            return

        combined = f"User: {user_message}\nAssistant: {assistant_message}"
        content_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]

        metadata = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if agent_id:
            metadata["agent_id"] = agent_id

        doc_id = self._store.add(
            text=combined,
            metadata=metadata,
            namespace=namespace,
        )

        # Store metadata in relational DB for management/querying
        if db is not None and doc_id:
            entry = MemoryEntry(
                session_id=session_id,
                agent_id=agent_id,
                content_hash=content_hash,
                content_preview=combined[:200],
                source_type="message",
            )
            db.add(entry)
            await db.commit()

        logger.debug("Ingested memory: %s (session=%s)", doc_id, session_id)
