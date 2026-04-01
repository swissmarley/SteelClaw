# Image Analyzer

Describe and inspect image files, returning metadata and file information.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: image, describe image, image info, image metadata, analyze image, picture

## System Prompt
You can inspect image files using the describe_image tool. It returns file metadata
including size, format, and dimensions (if PIL/Pillow is available). Also provides
a base64-encoded preview reference for further processing.

## Tools

### describe_image
Read an image file and return its metadata and base64 info.

**Parameters:**
- `file_path` (string, required): Absolute path to the image file
