"""Tests for VikingStore — uses mocked openviking client."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from steelclaw.settings import MemorySettings


# ── Category classifier ──────────────────────────────────────────────────────

def test_classify_default_is_events():
    from steelclaw.memory.viking_store import classify_category
    assert classify_category("Hello, how are you today?") == "events"


def test_classify_profile():
    from steelclaw.memory.viking_store import classify_category
    assert classify_category("I am a software engineer") == "profile"
    assert classify_category("My name is Alice") == "profile"


def test_classify_preferences():
    from steelclaw.memory.viking_store import classify_category
    assert classify_category("I prefer Python over Java") == "preferences"
    assert classify_category("I like dark mode editors") == "preferences"


def test_classify_cases():
    from steelclaw.memory.viking_store import classify_category
    assert classify_category("There was an error in the deployment") == "cases"
    assert classify_category("Fixed the bug in the auth module") == "cases"


def test_classify_patterns():
    from steelclaw.memory.viking_store import classify_category
    assert classify_category("I always use pytest for testing") == "patterns"


# ── Availability without server ───────────────────────────────────────────────

def test_viking_store_unavailable_when_disabled():
    from steelclaw.memory.viking_store import VikingStore
    store = VikingStore(MemorySettings(enabled=False))
    assert store.available is False


def test_viking_store_unavailable_when_openviking_missing():
    import steelclaw.memory.viking_store as vs_mod
    with patch.object(vs_mod, "_openviking_available", False):
        from steelclaw.memory.viking_store import VikingStore
        store = VikingStore(MemorySettings(backend="openviking"))
        assert store.available is False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_store(mock_session, tier="L1"):
    """Build a VikingStore bypassing actual openviking import."""
    from steelclaw.memory.viking_store import VikingStore
    settings = MemorySettings(
        backend="openviking",
        openviking_server_url="http://localhost:1933",
        openviking_workspace="test_ws",
        openviking_context_tier=tier,
    )
    store = VikingStore.__new__(VikingStore)
    store._settings = settings
    store._client = MagicMock()
    store._session = mock_session
    return store


# ── Functional tests with mocked session ─────────────────────────────────────

def test_available_is_true_with_mock_session():
    mock_session = MagicMock()
    store = _make_store(mock_session)
    assert store.available is True


def test_add_calls_session_add_with_uri():
    mock_session = MagicMock()
    store = _make_store(mock_session)
    result = store.add(text="Hello world", metadata={"session_id": "s1"})
    assert result is not None
    mock_session.add.assert_called_once()
    kwargs = mock_session.add.call_args.kwargs
    assert kwargs["uri"].startswith("viking://memory/")
    assert kwargs["content"] == "Hello world"


def test_add_profile_text_uses_profile_category():
    mock_session = MagicMock()
    store = _make_store(mock_session)
    store.add(text="I am a software developer", metadata={})
    uri = mock_session.add.call_args.kwargs["uri"]
    assert "/profile/" in uri


def test_add_returns_none_on_session_error():
    mock_session = MagicMock()
    mock_session.add.side_effect = RuntimeError("server error")
    store = _make_store(mock_session)
    assert store.add(text="some text") is None


def test_query_returns_formatted_dicts():
    mock_session = MagicMock()
    mock_session.search.return_value = [
        {
            "uri": "viking://memory/events/abc123",
            "content": "User: hi\nAssistant: hello",
            "metadata": {"session_id": "s1"},
            "score": 0.9,
        }
    ]
    store = _make_store(mock_session)
    results = store.query("hello", n_results=3)
    assert len(results) == 1
    r = results[0]
    assert r["id"] == "abc123"
    assert r["document"] == "User: hi\nAssistant: hello"
    assert r["metadata"] == {"session_id": "s1"}
    assert abs(r["distance"] - 0.1) < 1e-9  # 1.0 - 0.9 = 0.1


def test_query_passes_tier_from_settings():
    mock_session = MagicMock()
    mock_session.search.return_value = []
    store = _make_store(mock_session, tier="L2")
    store.query("test", n_results=5)
    mock_session.search.assert_called_once_with("test", n=5, tier="L2")


def test_query_returns_empty_on_error():
    mock_session = MagicMock()
    mock_session.search.side_effect = RuntimeError("server error")
    store = _make_store(mock_session)
    assert store.query("test") == []


def test_delete_iterates_all_categories():
    from steelclaw.memory.viking_store import VALID_CATEGORIES
    mock_session = MagicMock()
    store = _make_store(mock_session)
    store.delete(["doc1"])
    assert mock_session.delete.call_count == len(VALID_CATEGORIES)


def test_count_delegates_to_session():
    mock_session = MagicMock()
    mock_session.count.return_value = 42
    store = _make_store(mock_session)
    assert store.count() == 42


def test_count_returns_zero_on_error():
    mock_session = MagicMock()
    mock_session.count.side_effect = RuntimeError("error")
    store = _make_store(mock_session)
    assert store.count() == 0


def test_clear_delegates_to_session():
    mock_session = MagicMock()
    store = _make_store(mock_session)
    store.clear()
    mock_session.clear.assert_called_once()


def test_commit_session_delegates():
    mock_session = MagicMock()
    store = _make_store(mock_session)
    store.commit_session()
    mock_session.commit.assert_called_once()


def test_commit_session_no_op_when_unavailable():
    from steelclaw.memory.viking_store import VikingStore
    store = VikingStore(MemorySettings(enabled=False))
    store.commit_session()  # must not raise


def test_no_op_methods_when_unavailable():
    from steelclaw.memory.viking_store import VikingStore
    store = VikingStore(MemorySettings(enabled=False))
    assert store.add("x") is None
    assert store.query("x") == []
    assert store.count() == 0
    store.delete(["x"])  # must not raise
    store.clear()        # must not raise


# ── Duck-typing compatibility ────────────────────────────────────────────────

def test_memory_ingestor_accepts_viking_store():
    from steelclaw.memory.ingestion import MemoryIngestor
    mock_session = MagicMock()
    store = _make_store(mock_session)
    ingestor = MemoryIngestor(store)
    assert ingestor._store is store


def test_memory_retriever_accepts_viking_store():
    from steelclaw.memory.retrieval import MemoryRetriever
    mock_session = MagicMock()
    store = _make_store(mock_session)
    retriever = MemoryRetriever(store)
    assert retriever._store is store


# ── Integration: ingest + retrieve ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_and_retrieve_round_trip():
    from steelclaw.memory.ingestion import MemoryIngestor
    from steelclaw.memory.retrieval import MemoryRetriever
    mock_session = MagicMock()
    mock_session.add.return_value = None
    mock_session.search.return_value = [
        {
            "uri": "viking://memory/events/abc123",
            "content": "User: what is 2+2?\nAssistant: 4",
            "metadata": {"session_id": "s1"},
            "score": 0.95,
        }
    ]
    store = _make_store(mock_session)
    ingestor = MemoryIngestor(store)
    retriever = MemoryRetriever(store)

    await ingestor.ingest_exchange(
        user_message="what is 2+2?",
        assistant_message="4",
        session_id="s1",
    )
    assert mock_session.add.called

    memories = retriever.retrieve_relevant("arithmetic question")
    assert len(memories) == 1
    assert "2+2" in memories[0]

    formatted = retriever.format_for_prompt(memories)
    assert "[Relevant context from previous conversations:]" in formatted


# ── Backend factory ──────────────────────────────────────────────────────────

def test_factory_returns_vector_store_for_chromadb():
    from steelclaw.app import _create_memory_store
    from steelclaw.memory.vector_store import VectorStore
    store = _create_memory_store(MemorySettings(backend="chromadb"))
    assert isinstance(store, VectorStore)


def test_factory_returns_viking_store_for_openviking():
    from steelclaw.app import _create_memory_store
    from steelclaw.memory.viking_store import VikingStore
    store = _create_memory_store(MemorySettings(backend="openviking"))
    assert isinstance(store, VikingStore)
    # VikingStore.available may be False (no server running in tests) — that's OK
