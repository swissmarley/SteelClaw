# PDF Reader

Extract text content from PDF files.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: pdf, read pdf, extract pdf, pdf text, parse pdf

## System Prompt
You can extract text from PDF files using the extract_text tool.
Provide a file path to a PDF and get the full text content back.
Requires pdfplumber (pip install pdfplumber) for best results.

## Tools

### extract_text
Extract all text content from a PDF file.

**Parameters:**
- `file_path` (string, required): Absolute path to the PDF file
