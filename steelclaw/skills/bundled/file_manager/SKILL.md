# File Manager

Read, write, copy, move, and manage files on the local filesystem.

## Metadata
- version: 1.2.0
- author: SteelClaw
- triggers: file, read, write, copy, move, save, list files, directory, ls, cat

## System Prompt
You can read, write, copy, move, and list files on the user's local filesystem.

When the user sends an attachment through a messenger connector (Telegram, Discord, Slack,
etc.) the file is automatically downloaded and its local path is shown in the message
context as `local_path`. To save that file to a permanent location use `copy_file` with
the `local_path` as the source — do NOT use `write_file` for binary files (images, audio,
PDFs) because it only handles text.

Always confirm before writing, copying, moving, or deleting files unless the user has
already given explicit confirmation.

## Tools

### read_file
Read the contents of a text file.

**Parameters:**
- `path` (string, required): Path to the file to read
- `max_lines` (integer): Maximum number of lines to return (default: 200)

### write_file
Write text content to a file, creating parent directories as needed.
Use this for text files only. For binary files (images, audio, PDFs) received
as attachments, use `copy_file` instead.

**Parameters:**
- `path` (string, required): Destination path
- `content` (string, required): Text content to write

### write_files
Write multiple files in a single operation. Useful for scaffolding projects
with multiple files. Parent directories are created automatically for each file.

**Parameters:**
- `files` (object, required): Dictionary mapping file paths to their content
  (e.g., {"src/main.py": "print('hello')", "README.md": "# My Project"})

### write_files
Write multiple files in a single operation. This is efficient for scaffolding
projects or creating multi-file code structures. Parent directories are created
automatically for each file.

**Parameters:**
- `files` (object, required): Dictionary mapping file paths to their content
  (e.g., {"src/app.py": "content", "src/utils.py": "content"})

### copy_file
Copy a file from source to destination, preserving binary content exactly.
This is the correct tool for saving attachment files (images, audio, PDFs, etc.)
that the agent received via a messenger connector. Parent directories are created
automatically.

**Parameters:**
- `source` (string, required): Source file path (e.g. the `local_path` from an attachment)
- `destination` (string, required): Destination file path

### move_file
Move (rename) a file from source to destination. Parent directories at the
destination are created automatically.

**Parameters:**
- `source` (string, required): Source file path
- `destination` (string, required): Destination file path

### create_directory
Create a directory and any missing parent directories.

**Parameters:**
- `path` (string, required): Directory path to create

### delete_file
Delete a single file. Will not delete directories.

**Parameters:**
- `path` (string, required): Path to the file to delete

### list_directory
List files and directories in a path.

**Parameters:**
- `path` (string): Directory path (default: current directory)
- `recursive` (boolean): Whether to list recursively (default: false)
