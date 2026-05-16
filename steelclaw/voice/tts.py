"""Text-to-speech via OpenAI TTS API."""

from __future__ import annotations

import logging
from pathlib import Path

from steelclaw.settings import VoiceSettings

logger = logging.getLogger("steelclaw.voice.tts")


class TextToSpeech:
    """Converts text to speech audio files using the OpenAI TTS API."""

    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings

    async def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str | None = None,
        response_format: str = "mp3",
    ) -> TTSResult:
        """Convert text to speech and save to a file.

        Requires: pip install 'steelclaw[voice]'
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return TTSResult(
                path="",
                error="OpenAI SDK not installed. Run: pip install 'steelclaw[voice]'",
            )

        try:
            client = AsyncOpenAI()
            response = await client.audio.speech.create(
                model=self._settings.tts_model,
                voice=voice or self._settings.tts_voice,
                input=text,
                response_format=response_format,
            )

            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            # Stream to file
            content = response.content if hasattr(response, "content") else await response.aread()
            out.write_bytes(content)

            logger.info("TTS saved to %s (%d bytes)", out, out.stat().st_size)
            return TTSResult(path=str(out))

        except Exception as e:
            logger.exception("TTS synthesis failed")
            return TTSResult(path="", error=str(e))


class TTSResult:
    def __init__(self, path: str, error: str = "") -> None:
        self.path = path
        self.error = error

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        d = {"path": self.path}
        if self.error:
            d["error"] = self.error
        return d
