"""Notes skill — persistent local note storage."""

from __future__ import annotations

import re
from pathlib import Path

NOTES_DIR = Path("data/notes")


def _ensure_dir() -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    name = re.sub(r"[^\w\s-]", "", title.lower())
    name = re.sub(r"\s+", "-", name.strip())
    return name[:100] or "untitled"


async def tool_create_note(title: str, content: str) -> str:
    """Create or overwrite a note."""
    _ensure_dir()
    filename = _safe_filename(title) + ".md"
    path = NOTES_DIR / filename
    path.write_text(f"# {title}\n\n{content}", encoding="utf-8")
    return f"Note saved: {filename}"


async def tool_read_note(title: str) -> str:
    """Read a note by title."""
    _ensure_dir()
    filename = _safe_filename(title) + ".md"
    path = NOTES_DIR / filename
    if not path.exists():
        # Try fuzzy match
        matches = [f for f in NOTES_DIR.glob("*.md") if _safe_filename(title) in f.stem]
        if matches:
            path = matches[0]
        else:
            return f"Note not found: {title}"
    return path.read_text(encoding="utf-8")


async def tool_list_notes() -> str:
    """List all saved notes."""
    _ensure_dir()
    notes = sorted(NOTES_DIR.glob("*.md"))
    if not notes:
        return "No notes saved yet."
    lines = ["Saved notes:\n"]
    for n in notes:
        first_line = n.read_text(encoding="utf-8").split("\n")[0].lstrip("# ").strip()
        size = n.stat().st_size
        lines.append(f"- **{first_line or n.stem}** ({size} bytes)")
    return "\n".join(lines)


async def tool_search_notes(query: str) -> str:
    """Search notes by keyword."""
    _ensure_dir()
    query_lower = query.lower()
    results = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        if query_lower in content.lower():
            title = content.split("\n")[0].lstrip("# ").strip()
            # Find the matching line for context
            for line in content.split("\n"):
                if query_lower in line.lower():
                    results.append(f"- **{title}**: ...{line.strip()[:100]}...")
                    break
    if not results:
        return f"No notes matching: {query}"
    return f"Notes matching '{query}':\n\n" + "\n".join(results)
