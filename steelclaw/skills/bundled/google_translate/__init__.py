"""Google Cloud Translation API integration — translate text and detect language."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

BASE_URL = "https://translation.googleapis.com/language/translate/v2"

required_credentials = [
    {"key": "api_key", "label": "Google Translate API Key", "type": "password"},
]


def _config() -> dict:
    return get_all_credentials("google_translate")


async def tool_translate_text(text: str, target_language: str, source_language: str = "") -> str:
    """Translate text to a target language using Google Cloud Translation."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure google_translate"
    try:
        params: dict = {
            "key": api_key,
            "q": text,
            "target": target_language,
            "format": "text",
        }
        if source_language:
            params["source"] = source_language
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            translations = data.get("data", {}).get("translations", [])
            if not translations:
                return "No translation returned."
            result = translations[0]
            translated = result.get("translatedText", "")
            detected = result.get("detectedSourceLanguage", source_language or "auto")
            return (
                f"Source language: {detected}\n"
                f"Target language: {target_language}\n"
                f"Translation: {translated}"
            )
    except Exception as e:
        return f"Error: {e}"


async def tool_detect_language(text: str) -> str:
    """Detect the language of a given text using Google Cloud Translation."""
    config = _config()
    api_key = config.get("api_key", "")
    if not api_key:
        return "Error: API key not configured. Run: steelclaw skills configure google_translate"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/detect",
                params={"key": api_key, "q": text},
            )
            resp.raise_for_status()
            data = resp.json()
            detections = data.get("data", {}).get("detections", [])
            if not detections or not detections[0]:
                return "Could not detect language."
            lines = []
            for det in detections[0]:
                lang = det.get("language", "unknown")
                confidence = det.get("confidence", 0)
                lines.append(f"- {lang}: {confidence:.2%} confidence")
            return "Detected languages:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
