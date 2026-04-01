"""Image Analyzer skill — describe images and extract metadata."""

from __future__ import annotations

import base64
import os


async def tool_describe_image(file_path: str) -> str:
    """Read an image file and return its metadata and base64 info."""
    try:
        if not os.path.isfile(file_path):
            return f"Error: File not found: {file_path}"

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lower()

        info_lines = [
            f"File: {file_name}",
            f"Path: {file_path}",
            f"Size: {file_size:,} bytes ({file_size / 1024:.1f} KB)",
            f"Extension: {ext}",
        ]

        # Try to get dimensions with PIL
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                width, height = img.size
                info_lines.append(f"Dimensions: {width} x {height} pixels")
                info_lines.append(f"Format: {img.format}")
                info_lines.append(f"Mode: {img.mode}")
                if hasattr(img, "info"):
                    dpi = img.info.get("dpi")
                    if dpi:
                        info_lines.append(f"DPI: {dpi}")
        except ImportError:
            info_lines.append("(Install Pillow for dimensions: pip install Pillow)")
        except Exception:
            info_lines.append("(Could not read image dimensions)")

        # Base64 encoding info
        with open(file_path, "rb") as f:
            raw = f.read()
        b64_length = len(base64.b64encode(raw))
        info_lines.append(f"Base64 length: {b64_length:,} characters")

        # MIME type guess
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
            ".svg": "image/svg+xml", ".tiff": "image/tiff", ".ico": "image/x-icon",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        info_lines.append(f"MIME type: {mime}")

        return "\n".join(info_lines)
    except Exception as e:
        return f"Error analyzing image: {e}"
