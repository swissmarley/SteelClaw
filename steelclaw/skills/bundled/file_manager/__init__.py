"""File manager skill — read, write, and list files."""

from __future__ import annotations

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
    """Write content to a file."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} characters to {p}"
    except Exception as e:
        return f"Error writing {path}: {e}"


async def tool_list_directory(path: str = ".", recursive: bool = False) -> str:
    """List files and directories."""
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
