"""ElevenLabs TTS integration — text to speech and list voices."""

from __future__ import annotations

import base64

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://api.elevenlabs.io/v1"

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

required_credentials = [
    {"key": "api_key", "label": "ElevenLabs API Key", "type": "password", "test_url": "https://api.elevenlabs.io/v1/voices"},
]


def _config() -> dict:
    return get_all_credentials("elevenlabs")


def _headers(api_key: str) -> dict:
    return {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }


async def tool_text_to_speech(text: str, voice_id: str = DEFAULT_VOICE_ID, model_id: str = "eleven_monolingual_v1") -> str:
    """Convert text to speech using ElevenLabs. Returns base64-encoded audio."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure elevenlabs"
    try:
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/text-to-speech/{voice_id}",
                headers=_headers(api_key),
                json=payload,
            )
            resp.raise_for_status()
            audio_b64 = base64.b64encode(resp.content).decode()
            size_kb = len(resp.content) / 1024
            return (
                f"Audio generated successfully.\n"
                f"Voice ID: {voice_id}\n"
                f"Size: {size_kb:.1f} KB\n"
                f"Format: audio/mpeg\n"
                f"Base64 audio (first 100 chars): {audio_b64[:100]}..."
            )
    except Exception as e:
        return f"Error: {e}"


async def tool_list_voices() -> str:
    """List all available voices on ElevenLabs."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure elevenlabs"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_URL}/voices",
                headers=_headers(api_key),
            )
            resp.raise_for_status()
            voices = resp.json().get("voices", [])
            if not voices:
                return "No voices found."
            lines = []
            for v in voices:
                name = v.get("name", "Unnamed")
                voice_id = v.get("voice_id", "N/A")
                category = v.get("category", "N/A")
                labels = v.get("labels", {})
                accent = labels.get("accent", "N/A")
                gender = labels.get("gender", "N/A")
                lines.append(f"- {voice_id}: {name} ({gender}, {accent}) [{category}]")
            return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
