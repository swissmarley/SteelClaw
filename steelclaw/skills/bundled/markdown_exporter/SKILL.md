# Markdown Exporter

Export text content to Markdown and HTML files.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: export, markdown, html, save markdown, convert html, export file

## System Prompt
You can export content to files. Use export_markdown to save Markdown content to a .md file,
or export_html to save content wrapped in a clean HTML template. Both tools write directly
to disk — no extra dependencies required.

## Tools

### export_markdown
Write Markdown content to a file.

**Parameters:**
- `content` (string, required): The Markdown content to write
- `output_path` (string, required): Absolute file path for the output .md file

### export_html
Write content wrapped in an HTML template to a file.

**Parameters:**
- `content` (string, required): The HTML body content to write
- `output_path` (string, required): Absolute file path for the output .html file
