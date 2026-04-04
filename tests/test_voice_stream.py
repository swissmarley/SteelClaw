import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from steelclaw.api.voice import split_into_chunks
from steelclaw.settings import (
    AgentSettings, DatabaseSettings, GatewaySettings,
    LLMSettings, Settings, VoiceSettings,
)


def test_split_basic_sentences():
    text = "Hello world. How are you? I am fine!"
    chunks = split_into_chunks(text)
    assert chunks == ["Hello world.", "How are you?", "I am fine!"]


def test_split_merges_short_chunks():
    text = "Hi. OK. This is a longer sentence that should stand alone."
    chunks = split_into_chunks(text, min_length=10)
    assert chunks == ["Hi. OK.", "This is a longer sentence that should stand alone."]


def test_split_single_sentence():
    text = "Just one sentence here"
    chunks = split_into_chunks(text)
    assert chunks == ["Just one sentence here"]


def test_split_empty():
    assert split_into_chunks("") == []
    assert split_into_chunks("   ") == []


def test_voice_settings_realtime_defaults():
    s = VoiceSettings()
    assert s.realtime_model == "gpt-4o-realtime-preview"
    assert s.realtime_voice == "alloy"
    assert s.realtime_vad_threshold == 0.5
    assert s.realtime_silence_ms == 600
    assert s.realtime_prefix_padding_ms == 300


# ── Realtime session endpoint tests ──────────────────────────────────────────

def _make_voice_settings():
    return Settings(
        database=DatabaseSettings(url="sqlite+aiosqlite://", echo=False),
        gateway=GatewaySettings(dm_allowlist_enabled=False),
        agents=AgentSettings(
            llm=LLMSettings(api_key="sk-test-key"),
            voice=VoiceSettings(
                enabled=True,
                realtime_model="gpt-4o-realtime-preview",
                realtime_voice="alloy",
                realtime_vad_threshold=0.5,
                realtime_silence_ms=600,
                realtime_prefix_padding_ms=300,
            ),
        ),
    )


@pytest.fixture()
async def voice_client():
    from steelclaw.app import create_app
    app = create_app(_make_voice_settings())
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_realtime_session_disabled():
    """Returns 400 when voice.enabled is False."""
    from steelclaw.app import create_app
    app = create_app(Settings(
        database=DatabaseSettings(url="sqlite+aiosqlite://", echo=False),
        gateway=GatewaySettings(dm_allowlist_enabled=False),
        agents=AgentSettings(voice=VoiceSettings(enabled=False)),
    ))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/voice/realtime-session",
                json={},
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 400


async def test_realtime_session_success(voice_client):
    """Returns client_secret and session_id on success."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "sess_abc123",
        "client_secret": {"value": "ek_test_token"},
        "model": "gpt-4o-realtime-preview",
    }

    with patch("steelclaw.api.voice.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp

        resp = await voice_client.post(
            "/api/voice/realtime-session",
            json={"voice": "alloy"},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess_abc123"
    assert data["client_secret"]["value"] == "ek_test_token"
    assert data["model"] == "gpt-4o-realtime-preview"


async def test_realtime_session_openai_error(voice_client):
    """Returns 502 when OpenAI returns a non-200 status."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("steelclaw.api.voice.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.return_value = mock_resp

        resp = await voice_client.post(
            "/api/voice/realtime-session",
            json={},
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 502


async def test_realtime_session_uses_agent_system_prompt(voice_client):
    """Verifies a non-empty system_prompt is passed to OpenAI."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "sess_xyz",
        "client_secret": {"value": "ek_xyz"},
        "model": "gpt-4o-realtime-preview",
    }
    captured = {}

    async def capture_post(url, **kwargs):
        captured["payload"] = kwargs.get("json", {})
        return mock_resp

    with patch("steelclaw.api.voice.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = instance
        instance.post.side_effect = capture_post

        await voice_client.post(
            "/api/voice/realtime-session",
            json={},
            headers={"Content-Type": "application/json"},
        )

    assert "instructions" in captured.get("payload", {})
    assert len(captured["payload"]["instructions"]) > 0
