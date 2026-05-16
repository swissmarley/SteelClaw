"""Memory retrieval — fetches relevant past context for LLM prompts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from steelclaw.memory.vector_store import VectorStore

if TYPE_CHECKING:
    from steelclaw.memory.viking_store import VikingStore

logger = logging.getLogger("steelclaw.memory")


class MemoryRetriever:
    """Retrieves relevant memories from the vector store to inject into context."""

    def __init__(self, vector_store: "VectorStore | VikingStore") -> None:
        self._store = vector_store

    def retrieve_relevant(
        self,
        query_text: str,
        namespace: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        """Query the vector store for relevant past exchanges.

        Returns formatted text snippets ready to inject into the system prompt.
        """
        if not self._store.available or not query_text.strip():
            return []

        results = self._store.query(
            text=query_text,
            n_results=limit,
            namespace=namespace,
        )

        if not results:
            return []

        memories = []
        for doc in results:
            # Filter out very distant matches (cosine distance > 0.8)
            if doc.get("distance", 1.0) > 0.8:
                continue
            memories.append(doc["document"])

        if memories:
            logger.debug(
                "Retrieved %d relevant memories for query: %.50s...",
                len(memories),
                query_text,
            )

        return memories

    def format_for_prompt(self, memories: list[str]) -> str:
        """Format retrieved memories as a context block for the system prompt."""
        if not memories:
            return ""

        lines = ["[Relevant context from previous conversations:]"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"  ({i}) {mem}")
        lines.append("[End of previous context]")
        return "\n".join(lines)

    async def retrieve_experiences(
        self,
        query: str,
        tags: list[str] | None = None,
        limit: int = 3,
        namespace: str = "experiences",
    ) -> list[tuple[str, dict]]:
        """Retrieve relevant past experiences for a similar task.

        Args:
            query: Task description or keywords
            tags: Optional tags to filter by
            limit: Maximum number of experiences to return
            namespace: Vector store namespace (default: "experiences")

        Returns:
            List of (experience_text, metadata) tuples
        """
        if not self._store.available:
            return []

        # Build filter for experiences
        where_filter = {"source_type": "experience"}

        try:
            results = self._store.query(
                text=query,
                n_results=limit,
                namespace=namespace,
                where=where_filter,
            )

            experiences = []
            for doc in results:
                # Filter out very distant matches
                if doc.get("distance", 1.0) > 0.8:
                    continue
                text = doc.get("document", "")
                if text:
                    experiences.append((text, doc.get("metadata", {})))

            if experiences:
                logger.debug(
                    "Retrieved %d experiences for query: %.50s...",
                    len(experiences),
                    query,
                )

            return experiences

        except Exception as e:
            logger.warning("Experience retrieval failed: %s", e)
            return []

    def format_experiences_for_prompt(
        self,
        experiences: list[tuple[str, dict]],
    ) -> str:
        """Format retrieved experiences as a context block for the system prompt."""
        if not experiences:
            return ""

        lines = ["[Past relevant experiences:]"]
        for i, (text, meta) in enumerate(experiences, 1):
            outcome = meta.get("outcome", "unknown")
            tags_str = ", ".join(meta.get("tags", []))
            lines.append(f"  ({i}) [{outcome}] {meta.get('task_summary', 'Task')}")
            if tags_str:
                lines.append(f"      Tags: {tags_str}")
        lines.append("[End of past experiences]")
        return "\n".join(lines)