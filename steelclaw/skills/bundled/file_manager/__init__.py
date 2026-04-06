"""File manager skill — read, write, copy, move, and list files."""

from __future__ import annotations

import shutil
from pathlib import Path


async def tool_read_file(path: str, max_lines: int = 200) -> str:
    """Read a file's contents."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines])
            text += f"\n\n... [truncated, {len(lines) - max_lines} more lines]"
        return f"File: {p}\n\n{text}"
    except Exception as e:
        return f"Error reading {path}: {e}"


async def tool_write_file(path: str, content: str) -> str:
    """Write text content to a file, creating parent directories as needed."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} characters to {p}"
    except Exception as e:
        return f"Error writing {path}: {e}"


async def tool_copy_file(source: str, destination: str) -> str:
    """Copy a file from source to destination, preserving binary content.

    Use this to save attachment files (images, audio, PDFs, etc.) that the
    agent received via a messenger connector.  The source is typically the
    ``local_path`` reported in the attachment metadata.  Parent directories
    are created automatically.
    """
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()

    if not src.exists():
        return f"Error: source file not found: {source}"
    if not src.is_file():
        return f"Error: source is not a file: {source}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        size = dst.stat().st_size
        size_str = (
            f"{size}B" if size < 1024
            else f"{size / 1024:.1f}KB" if size < 1024 * 1024
            else f"{size / (1024 * 1024):.1f}MB"
        )
        return f"Copied {src.name} → {dst} ({size_str})"
    except Exception as e:
        return f"Error copying {source} → {destination}: {e}"


async def tool_move_file(source: str, destination: str) -> str:
    """Move (rename) a file from source to destination.

    Parent directories at the destination are created automatically.
    """
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()

    if not src.exists():
        return f"Error: source not found: {source}"
    if not src.is_file():
        return f"Error: source is not a file: {source}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {src} → {dst}"
    except Exception as e:
        return f"Error moving {source} → {destination}: {e}"


async def tool_create_directory(path: str) -> str:
    """Create a directory and any missing parent directories."""
    p = Path(path).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {p}"
    except Exception as e:
        return f"Error creating directory {path}: {e}"


async def tool_delete_file(path: str) -> str:
    """Delete a file.  Will not delete directories."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file (use a different approach for directories): {path}"
    try:
        p.unlink()
        return f"Deleted: {p}"
    except Exception as e:
        return f"Error deleting {path}: {e}"


async def tool_list_directory(path: str = ".", recursive: bool = False) -> str:
    """List files and directories in a path."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"Directory not found: {path}"
    if not p.is_dir():
        return f"Not a directory: {path}"

    try:
        items = sorted(p.rglob("*") if recursive else p.iterdir())
        # Limit output
        max_items = 100
        lines = [f"Contents of {p}:\n"]
        for i, item in enumerate(items):
            if i >= max_items:
                lines.append(f"\n... and {len(items) - max_items} more items")
                break
            rel = item.relative_to(p)
            if item.is_dir():
                lines.append(f"  [dir]  {rel}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
                lines.append(f"  {size_str:>8}  {rel}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing {path}: {e}"
