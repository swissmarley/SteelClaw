"""Attachment classification, download, and transcription helpers for messenger connectors.

Provides utilities to:
- Categorise a file by its MIME type or extension
- Build the normalised attachment dict expected by InboundMessage.attachments
  and ContextBuilder._build_user_message
- Save attachment bytes to a local temp file so the agent can manipulate them
- Transcribe audio attachments via the Whisper-based voice transcription stack
"""

from __future__ import annotations

import base64
import csv
import io
import logging
import os
import tempfile

logger = logging.getLogger("steelclaw.gateway.attachments")

# MIME type → attachment category
_MIME_TO_CATEGORY: dict[str, str] = {
    # images
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "image/bmp": "image",
    "image/tiff": "image",
    "image/svg+xml": "image",
    "image/heic": "image",
    "image/heif": "image",
    # audio
    "audio/mpeg": "audio",
    "audio/mp3": "audio",
    "audio/ogg": "audio",
    "audio/wav": "audio",
    "audio/webm": "audio",
    "audio/flac": "audio",
    "audio/aac": "audio",
    "audio/opus": "audio",
    "audio/x-m4a": "audio",
    "audio/mp4": "audio",
    # video
    "video/mp4": "video",
    "video/mpeg": "video",
    "video/webm": "video",
    "video/ogg": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video",
    "video/x-matroska": "video",
    # csv
    "text/csv": "csv",
    "application/csv": "csv",
    # documents
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.ms-excel": "document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
    "text/plain": "document",
    "text/markdown": "document",
    "application/json": "document",
    "application/xml": "document",
    "text/xml": "document",
}

# File extension → category (fallback when MIME is absent or generic)
_EXT_TO_CATEGORY: dict[str, str] = {
    # images
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
    ".webp": "image", ".bmp": "image", ".tiff": "image", ".tif": "image",
    ".svg": "image", ".heic": "image", ".heif": "image",
    # audio
    ".mp3": "audio", ".ogg": "audio", ".oga": "audio", ".wav": "audio",
    ".flac": "audio", ".aac": "audio", ".opus": "audio", ".m4a": "audio",
    ".wma": "audio",
    # video
    ".mp4": "video", ".mpeg": "video", ".mpg": "video", ".webm": "video",
    ".mov": "video", ".avi": "video", ".mkv": "video", ".flv": "video",
    # csv
    ".csv": "csv",
    # documents
    ".pdf": "document", ".doc": "document", ".docx": "document",
    ".txt": "document", ".md": "document", ".json": "document",
    ".xml": "document", ".xls": "document", ".xlsx": "document",
}


def categorize_file(filename: str, mime_type: str | None = None) -> str:
    """Return the category for a file.

    Returns one of: ``'image'``, ``'audio'``, ``'video'``, ``'document'``,
    ``'csv'``, or ``'unknown'``.
    """
    if mime_type:
        # Strip parameters (e.g. "text/plain; charset=utf-8" → "text/plain")
        base_mime = mime_type.lower().split(";")[0].strip()
        category = _MIME_TO_CATEGORY.get(base_mime)
        if category:
            return category
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    return _EXT_TO_CATEGORY.get(ext, "unknown")


def build_attachment_dict(
    filename: str,
    mime: str | None,
    data: bytes | None = None,
) -> dict:
    """Build a normalised attachment dict for ``InboundMessage.attachments``.

    Keys set on the returned dict:

    * ``filename`` (str)
    * ``mime`` (str)
    * ``category`` (str) — one of image / audio / video / document / csv / unknown
    * ``base64`` (str | None) — base64-encoded bytes, images only
    * ``text_content`` (str | None) — extracted text, documents and CSV only
    * ``local_path`` (str | None) — path to a temp file containing the raw bytes
      (set for all categories when ``data`` is provided so the agent can
      read/copy/move the file via filesystem tools)
    """
    category = categorize_file(filename, mime)
    att: dict = {
        "filename": filename,
        "mime": mime or "application/octet-stream",
        "category": category,
    }

    if data:
        # Always persist a temp copy so the agent has a real filesystem path
        att["local_path"] = _save_temp_file(data, filename)

        if category == "image":
            att["base64"] = base64.b64encode(data).decode()
        elif category == "csv":
            att["text_content"] = _extract_csv_preview(data, filename)
        elif category == "document":
            att["text_content"] = _extract_document_text(data, filename)
        # audio / video / unknown — local_path already set; transcription is
        # handled asynchronously by the connector after this call returns

    return att


# ── Temp-file helper ─────────────────────────────────────────────────────────


def _save_temp_file(data: bytes, filename: str) -> str | None:
    """Write *data* to a temporary file and return its path.

    The caller is responsible for eventual cleanup; the OS will remove files in
    the system temp directory on the next reboot at the latest.
    """
    try:
        suffix = os.path.splitext(filename)[1] or ""
        with tempfile.NamedTemporaryFile(
            suffix=suffix, prefix="steelclaw_att_", delete=False
        ) as tmp:
            tmp.write(data)
            return tmp.name
    except Exception:
        logger.debug("Could not save attachment '%s' to temp file", filename, exc_info=True)
        return None


# ── Audio transcription ──────────────────────────────────────────────────────


async def transcribe_audio_attachment(
    data: bytes,
    filename: str,
) -> str | None:
    """Transcribe *data* (raw audio bytes) using the Whisper-based stack.

    Returns the transcribed text on success, ``None`` if transcription is not
    configured or fails (e.g. no Whisper API key set).  Errors are logged at
    DEBUG level and never raised so the caller can always fall back gracefully.
    """
    try:
        from steelclaw.settings import VoiceSettings
        from steelclaw.voice.transcription import Transcriber
    except ImportError:
        logger.debug("Voice transcription stack not available")
        return None

    suffix = os.path.splitext(filename)[1] or ".ogg"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        transcriber = Transcriber(VoiceSettings())
        result = await transcriber.transcribe(tmp_path)
        if result.ok:
            logger.info(
                "Transcribed audio attachment '%s': %d chars", filename, len(result.text)
            )
            return result.text
        else:
            logger.debug(
                "Transcription returned no text for '%s': %s", filename, result.error
            )
            return None
    except Exception:
        logger.debug("Audio transcription failed for '%s'", filename, exc_info=True)
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ── Text extraction helpers ──────────────────────────────────────────────────

_MAX_TEXT_CHARS = 4096


def _extract_csv_preview(data: bytes, filename: str) -> str | None:
    """Return a plain-text preview of a CSV file (header + first rows)."""
    try:
        text = data.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        preview = rows[:6]
        result = "\n".join(",".join(cell for cell in row) for row in preview)
        if len(rows) > 6:
            result += f"\n… ({len(rows)} rows total)"
        return result
    except Exception:
        logger.debug("Could not parse CSV '%s'", filename, exc_info=True)
        return None


def _extract_document_text(data: bytes, filename: str) -> str | None:
    """Extract text from document bytes.

    Supports PDF (via pypdf or PyPDF2 if installed), plain text, Markdown, JSON.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf_text(data)
    if lower.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    if lower.endswith(".json"):
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    if lower.endswith((".xml",)):
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    # Fallback: try UTF-8 decode
    try:
        return data.decode("utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    except Exception:
        return None


def _extract_pdf_text(data: bytes) -> str | None:
    """Extract text from a PDF, trying pypdf then PyPDF2."""
    # Try pypdf (modern fork)
    try:
        import pypdf  # noqa: F401
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages[:10]]
        return "\n".join(pages_text)[:_MAX_TEXT_CHARS]
    except ImportError:
        pass
    except Exception:
        logger.debug("pypdf failed to extract text", exc_info=True)

    # Try PyPDF2 (legacy)
    try:
        import PyPDF2  # noqa: F401
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages[:10]]
        return "\n".join(pages_text)[:_MAX_TEXT_CHARS]
    except ImportError:
        pass
    except Exception:
        logger.debug("PyPDF2 failed to extract text", exc_info=True)

    return None
