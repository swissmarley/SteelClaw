"""Tests for MemorySettings — OpenViking backend fields."""

from steelclaw.settings import MemorySettings


def test_default_backend_is_chromadb():
    s = MemorySettings()
    assert s.backend == "chromadb"


def test_openviking_fields_have_defaults():
    s = MemorySettings()
    assert s.openviking_server_url == "http://localhost:1933"
    assert s.openviking_workspace == "steelclaw"
    assert s.openviking_context_tier == "L1"


def test_backend_can_be_set_to_openviking():
    s = MemorySettings(backend="openviking")
    assert s.backend == "openviking"


def test_existing_fields_unchanged():
    s = MemorySettings(chromadb_path="/tmp/chroma", collection_name="col", top_k=3)
    assert s.chromadb_path == "/tmp/chroma"
    assert s.collection_name == "col"
    assert s.top_k == 3
