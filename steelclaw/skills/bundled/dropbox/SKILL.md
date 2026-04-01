# Dropbox

Manage files on Dropbox — list folders, upload, and download files.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: dropbox, cloud storage, file sync, dropbox files

## System Prompt
You can use Dropbox. Credentials must be configured via `steelclaw skills configure dropbox`.

## Tools

### list_folder
List files and folders in a Dropbox path.

**Parameters:**
- `path` (string): Folder path (default: "" for root)

### upload_file
Upload a file to Dropbox.

**Parameters:**
- `local_path` (string, required): Local file path to upload
- `dropbox_path` (string, required): Destination path in Dropbox

### download_file
Download a file from Dropbox.

**Parameters:**
- `dropbox_path` (string, required): File path in Dropbox
- `local_path` (string, required): Local path to save the file
