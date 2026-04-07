"""Memory ingestion — stores conversation exchanges as vector embeddings."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import MemoryEntry
from steelclaw.memory.vector_store import VectorStore

if TYPE_CHECKING:
    from steelclaw.memory.viking_store import VikingStore

logger = logging.getLogger("steelclaw.memory")


class MemoryIngestor:
    """Ingests message pairs into the vector store for later retrieval."""

    def __init__(self, vector_store: "VectorStore | VikingStore") -> None:
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
        # Note: Caller is responsible for committing the transaction
        if db is not None and doc_id:
            entry = MemoryEntry(
                session_id=session_id,
                agent_id=agent_id,
                content_hash=content_hash,
                content_preview=combined[:200],
                source_type="message",
            )
            db.add(entry)

        logger.debug("Ingested memory: %s (session=%s)", doc_id, session_id)

    async def ingest_experience(
        self,
        task_summary: str,
        steps_taken: list[str],
        errors_encountered: list[str] | None,
        outcome: str,
        tags: list[str] | None,
        session_id: str,
        agent_id: str | None = None,
        namespace: str = "experiences",
        db: AsyncSession | None = None,
    ) -> str | None:
        """Store a completed task as an experience entry for future reference.

        Args:
            task_summary: Brief description of the task
            steps_taken: List of steps that were executed
            errors_encountered: List of errors encountered (if any)
            outcome: Result outcome - "success", "failure", or "partial"
            tags: Tags for categorization (e.g., ["web", "flask", "deployment"])
            session_id: Session ID
            agent_id: Agent ID (optional)
            namespace: Vector store namespace (default: "experiences")
            db: Database session for relational storage

        Returns:
            Document ID if successful, None otherwise
        """
        if not self._store.available:
            return None

        # Build experience text
        experience_text = f"Task: {task_summary}\n\nSteps:\n"
        for i, step in enumerate(steps_taken, 1):
            experience_text += f"{i}. {step}\n"

        if errors_encountered:
            experience_text += "\nErrors Encountered:\n"
            for error in errors_encountered:
                experience_text += f"- {error}\n"

        experience_text += f"\nOutcome: {outcome}"

        content_hash = hashlib.sha256(experience_text.encode()).hexdigest()[:16]

        # Build metadata
        metadata = {
            "source_type": "experience",
            "task_summary": task_summary,
            "outcome": outcome,
            "tags": tags or [],
            "steps_count": len(steps_taken),
            "errors_count": len(errors_encountered) if errors_encountered else 0,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if agent_id:
            metadata["agent_id"] = agent_id

        doc_id = self._store.add(
            text=experience_text,
            metadata=metadata,
            namespace=namespace,
        )

        # Store metadata in relational DB
        # Note: Caller is responsible for committing the transaction
        if db is not None and doc_id:
            entry = MemoryEntry(
                session_id=session_id,
                agent_id=agent_id,
                content_hash=content_hash,
                content_preview=experience_text[:200],
                source_type="experience",
                metadata_json=json.dumps({"tags": tags, "outcome": outcome}),
            )
            db.add(entry)

        logger.debug(
            "Ingested experience: %s (outcome=%s, tags=%s)",
            doc_id,
            outcome,
            tags,
        )
        return doc_id