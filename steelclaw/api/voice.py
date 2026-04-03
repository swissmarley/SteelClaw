"""REST API for voice — transcription and text-to-speech."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice: str = ""


@router.post("/transcribe")
async def transcribe_audio(request: Request, file: UploadFile = File(...)) -> dict:
    """Transcribe an uploaded audio file to text."""
    settings = request.app.state.settings.agents.voice

    if not settings.enabled:
        raise HTTPException(400, "Voice mode is not enabled in settings")

    from steelclaw.voice.transcription import Transcriber

    transcriber = Transcriber(settings)

    suffix = Path(file.filename or ".wav").suffix
    tmp = Path(tempfile.gettempdir()) / f"sc_voice_{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    tmp.write_bytes(content)

    try:
        result = await transcriber.transcribe(str(tmp))
        return result.to_dict()
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/synthesize")
async def synthesize_speech(request: Request, body: TTSRequest) -> FileResponse:
    """Convert text to speech and return audio file."""
    settings = request.app.state.settings.agents.voice

    if not settings.enabled:
        raise HTTPException(400, "Voice mode is not enabled in settings")

    from starlette.background import BackgroundTask

    from steelclaw.voice.tts import TextToSpeech

    tts = TextToSpeech(settings)

    output = Path(tempfile.gettempdir()) / f"sc_tts_{uuid.uuid4().hex}.mp3"
    result = await tts.synthesize(body.text, str(output), voice=body.voice or None)

    if not result.ok:
        output.unlink(missing_ok=True)
        raise HTTPException(500, result.error)

    # Clean up temp file after the response has been sent
    return FileResponse(
        str(output),
        media_type="audio/mpeg",
        filename="speech.mp3",
        background=BackgroundTask(lambda: output.unlink(missing_ok=True)),
    )


def split_into_chunks(text: str, min_length: int = 10) -> list[str]:
    """Split text into sentence-sized chunks for progressive TTS."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    merged: list[str] = []
    buffer = ""
    for part in parts:
        if buffer and len(part) >= min_length:
            merged.append(buffer)
            buffer = ""
        if buffer:
            buffer += " " + part
        else:
            buffer = part
        if len(buffer) >= min_length:
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] += " " + buffer
        else:
            merged.append(buffer)
    return merged


@router.post("/synthesize-stream")
async def synthesize_stream(request: Request, body: TTSRequest):
    """Stream TTS audio in sentence-sized chunks for low-latency playback."""
    settings = request.app.state.settings.agents.voice

    if not settings.enabled:
        raise HTTPException(400, "Voice mode is not enabled in settings")

    chunks = split_into_chunks(body.text)
    if not chunks:
        raise HTTPException(400, "No text to synthesize")

    async def generate():
        from steelclaw.voice.tts import TextToSpeech

        tts = TextToSpeech(settings)
        for chunk_text in chunks:
            output = Path(tempfile.gettempdir()) / f"sc_tts_{uuid.uuid4().hex}.mp3"
            result = await tts.synthesize(chunk_text, str(output), voice=body.voice or None)
            if result.ok:
                audio_bytes = output.read_bytes()
                yield audio_bytes
                output.unlink(missing_ok=True)

    return StreamingResponse(generate(), media_type="audio/mpeg")


class VoiceChatRequest(BaseModel):
    """Request for the streaming voice chat endpoint."""
    session_id: str = ""
    user_id: str = "voice-user"
    voice: str = ""


def _extract_sentences(buffer: str) -> tuple[list[str], str]:
    """Extract complete sentences from buffer, return (sentences, remainder)."""
    sentences = []
    # Split on sentence-ending punctuation followed by space or end
    parts = re.split(r'(?<=[.!?])\s+', buffer)
    if len(parts) <= 1:
        # No complete sentence yet
        return [], buffer
    # All but last are complete sentences
    sentences = parts[:-1]
    remainder = parts[-1]
    return sentences, remainder


@router.post("/chat-stream")
async def voice_chat_stream(request: Request, file: UploadFile = File(...)):
    """Full voice pipeline with minimal latency: transcribe → stream LLM → progressive TTS.

    Starts generating TTS audio as soon as the first sentence is available from the LLM,
    rather than waiting for the full response.
    """
    settings = request.app.state.settings

    if not settings.agents.voice.enabled:
        raise HTTPException(400, "Voice mode is not enabled in settings")

    # Step 1: Transcribe audio input
    from steelclaw.voice.transcription import Transcriber

    transcriber = Transcriber(settings.agents.voice)
    suffix = Path(file.filename or ".wav").suffix
    tmp = Path(tempfile.gettempdir()) / f"sc_voice_{uuid.uuid4().hex}{suffix}"
    content = await file.read()
    tmp.write_bytes(content)

    try:
        result = await transcriber.transcribe(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)

    if not result.text:
        raise HTTPException(400, "Could not transcribe audio")

    user_text = result.text

    # Step 2: Set up streaming LLM → progressive TTS
    from steelclaw.db.engine import get_async_session
    from steelclaw.gateway.router import process_message_streaming
    from steelclaw.schemas.messages import InboundMessage

    # Parse optional params from form data
    voice_param = request.query_params.get("voice", "")

    inbound = InboundMessage(
        platform="voice",
        platform_chat_id=request.query_params.get("session_id", "voice-session"),
        platform_user_id=request.query_params.get("user_id", "voice-user"),
        content=user_text,
        is_group=False,
        is_mention=False,
    )

    async def generate():
        """Stream TTS audio as sentences complete from the LLM."""
        from steelclaw.voice.tts import TextToSpeech

        tts = TextToSpeech(settings.agents.voice)
        text_buffer = ""

        async for db in get_async_session():
            async for event in process_message_streaming(
                inbound, settings.gateway, db
            ):
                if event.get("type") == "chunk":
                    text_buffer += event.get("content", "")

                    # Check for complete sentences
                    sentences, text_buffer = _extract_sentences(text_buffer)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if len(sentence) < 5:
                            continue
                        output = Path(tempfile.gettempdir()) / f"sc_tts_{uuid.uuid4().hex}.mp3"
                        tts_result = await tts.synthesize(
                            sentence, str(output),
                            voice=voice_param or None,
                        )
                        if tts_result.ok:
                            yield output.read_bytes()
                            output.unlink(missing_ok=True)

                elif event.get("type") in ("done", "error"):
                    # Synthesize any remaining text
                    remaining = text_buffer.strip()
                    if remaining and len(remaining) >= 5:
                        output = Path(tempfile.gettempdir()) / f"sc_tts_{uuid.uuid4().hex}.mp3"
                        tts_result = await tts.synthesize(
                            remaining, str(output),
                            voice=voice_param or None,
                        )
                        if tts_result.ok:
                            yield output.read_bytes()
                            output.unlink(missing_ok=True)
                    break

    return StreamingResponse(generate(), media_type="audio/mpeg")


@router.get("/status")
async def voice_status(request: Request) -> dict:
    """Return voice system status."""
    settings = request.app.state.settings.agents.voice
    return {
        "enabled": settings.enabled,
        "stt_provider": settings.stt_provider,
        "tts_provider": settings.tts_provider,
        "tts_model": settings.tts_model,
        "tts_voice": settings.tts_voice,
    }
