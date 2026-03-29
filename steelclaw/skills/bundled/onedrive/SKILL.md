# OneDrive

Manage files on Microsoft OneDrive via Microsoft Graph API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: onedrive, microsoft drive, office files, cloud storage

## System Prompt
You can use OneDrive. Credentials must be configured via `steelclaw skills configure onedrive`.

## Tools

### list_files
List files in OneDrive root or a specific folder.

**Parameters:**
- `folder_path` (string): Folder path (default: root)

### upload_file
Upload a file to OneDrive.

**Parameters:**
- `local_path` (string, required): Local file path to upload
- `remote_path` (string, required): Destination path in OneDrive
