# File Manager

Read, write, and manage files on the local filesystem.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: file, read, write, list files, directory, ls, cat

## System Prompt
You can read, write, and list files on the user's local filesystem.
Always confirm before writing or modifying files.
Do not access files outside the current working directory unless the user specifies an absolute path.

## Tools

### read_file
Read the contents of a file.

**Parameters:**
- `path` (string, required): Path to the file to read
- `max_lines` (integer): Maximum number of lines to return (default: 200)

### write_file
Write content to a file, creating it if it doesn't exist.

**Parameters:**
- `path` (string, required): Path to the file to write
- `content` (string, required): Content to write to the file

### list_directory
List files and directories in a path.

**Parameters:**
- `path` (string): Directory path (default: current directory)
- `recursive` (boolean): Whether to list recursively (default: false)
