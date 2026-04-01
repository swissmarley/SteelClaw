"""File Organizer skill — bulk file listing, renaming, and duplicate detection."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


async def tool_list_directory(path: str, pattern: str | None = None) -> str:
    """List files in a directory with optional glob pattern filtering."""
    try:
        p = Path(path)
        if not p.is_dir():
            return f"Error: Directory not found: {path}"

        if pattern:
            files = sorted(p.glob(pattern))
        else:
            files = sorted(p.iterdir())

        if not files:
            return f"No files found in {path}" + (f" matching '{pattern}'" if pattern else "")

        lines = [f"Directory: {path}"]
        if pattern:
            lines.append(f"Pattern: {pattern}")
        lines.append(f"Total: {len(files)} item(s)\n")

        for f in files[:500]:
            if f.is_dir():
                lines.append(f"  [DIR]  {f.name}/")
            else:
                size = f.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                lines.append(f"  {size_str:>10}  {f.name}")

        if len(files) > 500:
            lines.append(f"\n... and {len(files) - 500} more items")

        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"


async def tool_rename_files(path: str, pattern: str, replacement: str) -> str:
    """Rename files by replacing a pattern in filenames."""
    try:
        p = Path(path)
        if not p.is_dir():
            return f"Error: Directory not found: {path}"

        renamed = []
        skipped = []

        for f in sorted(p.iterdir()):
            if f.is_file() and pattern in f.name:
                new_name = f.name.replace(pattern, replacement)
                new_path = f.parent / new_name
                if new_path.exists():
                    skipped.append(f"  {f.name} -> {new_name} (target already exists)")
                else:
                    f.rename(new_path)
                    renamed.append(f"  {f.name} -> {new_name}")

        lines = []
        if renamed:
            lines.append(f"Renamed {len(renamed)} file(s):")
            lines.extend(renamed)
        if skipped:
            lines.append(f"\nSkipped {len(skipped)} file(s):")
            lines.extend(skipped)
        if not renamed and not skipped:
            lines.append(f"No files matching pattern '{pattern}' found in {path}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error renaming files: {e}"


async def tool_find_duplicates(path: str) -> str:
    """Find duplicate files by comparing content hashes."""
    try:
        p = Path(path)
        if not p.is_dir():
            return f"Error: Directory not found: {path}"

        hash_map: dict[str, list[str]] = {}
        file_count = 0

        for f in p.rglob("*"):
            if not f.is_file():
                continue
            file_count += 1
            try:
                h = hashlib.md5()
                with open(f, "rb") as fh:
                    while chunk := fh.read(8192):
                        h.update(chunk)
                digest = h.hexdigest()
                hash_map.setdefault(digest, []).append(str(f))
            except (PermissionError, OSError):
                continue

        duplicates = {k: v for k, v in hash_map.items() if len(v) > 1}

        if not duplicates:
            return f"No duplicates found among {file_count} files in {path}"

        lines = [f"Found {len(duplicates)} set(s) of duplicates among {file_count} files:\n"]
        for i, (digest, files) in enumerate(duplicates.items(), 1):
            size = os.path.getsize(files[0])
            lines.append(f"Set {i} (hash: {digest[:12]}..., size: {size:,} bytes):")
            for f in files:
                lines.append(f"  {f}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"Error finding duplicates: {e}"
