# File Organizer

Bulk file operations including listing, renaming, and duplicate detection.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: organize files, rename files, find duplicates, list files, bulk rename, file management

## System Prompt
You can perform bulk file operations: list directory contents with optional glob patterns,
rename files using pattern matching, and find duplicate files by content hash.
Uses Python stdlib (pathlib, hashlib) — no extra dependencies required.

## Tools

### list_directory
List files in a directory with optional glob pattern filtering.

**Parameters:**
- `path` (string, required): Absolute path to the directory
- `pattern` (string, optional): Glob pattern to filter files (e.g. "*.txt", "**/*.py")

### rename_files
Rename files in a directory by replacing a pattern in filenames.

**Parameters:**
- `path` (string, required): Absolute path to the directory
- `pattern` (string, required): Text pattern to find in filenames
- `replacement` (string, required): Replacement text

### find_duplicates
Find duplicate files in a directory by comparing content hashes.

**Parameters:**
- `path` (string, required): Absolute path to the directory to scan
