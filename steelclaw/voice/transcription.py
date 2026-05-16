"""Voice transcription via OpenAI Whisper API."""

from __future__ import annotations

import logging
from pathlib import Path

from steelclaw.settings import VoiceSettings

logger = logging.getLogger("steelclaw.voice.transcription")


class Transcriber:
    """Transcribes audio files to text using the Whisper API."""

    def __init__(self, settings: VoiceSettings) -> None:
        self._settings = settings

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Supports: mp3, mp4, mpeg, mpga, m4a, wav, webm
        Requires: pip install 'steelclaw[voice]'
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return TranscriptionResult(
                text="",
                error="OpenAI SDK not installed. Run: pip install 'steelclaw[voice]'",
            )

        path = Path(audio_path)
        if not path.exists():
            return TranscriptionResult(text="", error=f"File not found: {audio_path}")

        try:
            client = AsyncOpenAI()
            with open(path, "rb") as audio_file:
                kwargs = {
                    "model": self._settings.transcription_model,
                    "file": audio_file,
                }
                if language:
                    kwargs["language"] = language

                response = await client.audio.transcriptions.create(**kwargs)

            text = response.text if hasattr(response, "text") else str(response)
            logger.info("Transcribed %s: %d chars", path.name, len(text))
            return TranscriptionResult(text=text)

        except Exception as e:
            logger.exception("Transcription failed: %s", audio_path)
            return TranscriptionResult(text="", error=str(e))


class TranscriptionResult:
    def __init__(self, text: str, error: str = "") -> None:
        self.text = text
        self.error = error

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        d = {"text": self.text}
        if self.error:
            d["error"] = self.error
        return d
