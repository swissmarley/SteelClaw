"""Markdown Exporter skill — export content to Markdown and HTML files."""

from __future__ import annotations

import os

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Exported Document</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            line-height: 1.6;
            color: #333;
        }}
        pre {{
            background: #f4f4f4;
            padding: 16px;
            border-radius: 4px;
            overflow-x: auto;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background: #f4f4f4;
        }}
    </style>
</head>
<body>
{content}
</body>
</html>"""


async def tool_export_markdown(content: str, output_path: str) -> str:
    """Write Markdown content to a file."""
    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = os.path.getsize(output_path)
        return (
            f"Markdown exported successfully.\n"
            f"Path: {output_path}\n"
            f"Size: {file_size:,} bytes"
        )
    except Exception as e:
        return f"Error exporting Markdown: {e}"


async def tool_export_html(content: str, output_path: str) -> str:
    """Write content wrapped in an HTML template to a file."""
    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        html = _HTML_TEMPLATE.format(content=content)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        file_size = os.path.getsize(output_path)
        return (
            f"HTML exported successfully.\n"
            f"Path: {output_path}\n"
            f"Size: {file_size:,} bytes"
        )
    except Exception as e:
        return f"Error exporting HTML: {e}"
