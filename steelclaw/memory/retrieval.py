"""Memory retrieval — fetches relevant past context for LLM prompts."""

from __future__ import annotations

import logging

from steelclaw.memory.vector_store import VectorStore

logger = logging.getLogger("steelclaw.memory")


class MemoryRetriever:
    """Retrieves relevant memories from the vector store to inject into context."""

    def __init__(self, vector_store: VectorStore) -> None:
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
