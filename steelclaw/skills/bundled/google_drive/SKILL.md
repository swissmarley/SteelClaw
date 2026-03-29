# Google Drive

Manage files on Google Drive — list, upload, and download.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: google drive, drive, files, cloud storage, gdrive

## System Prompt
You can use Google Drive. Credentials must be configured via `steelclaw skills configure google_drive`.

## Tools

### list_files
List files in Google Drive.

**Parameters:**
- `query` (string): Search query using Drive query syntax
- `max_results` (integer): Maximum files to return (default: 20)

### upload_file
Upload a file to Google Drive.

**Parameters:**
- `file_path` (string, required): Local path to the file to upload
- `name` (string): Name for the file in Drive (default: local filename)
- `mime_type` (string): MIME type of the file

### download_file
Download a file from Google Drive by ID.

**Parameters:**
- `file_id` (string, required): The Drive file ID
- `output_path` (string, required): Local path to save the downloaded file
