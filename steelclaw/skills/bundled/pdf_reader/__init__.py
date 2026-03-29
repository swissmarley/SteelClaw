"""PDF Reader skill — extract text content from PDF files."""

from __future__ import annotations

import os


async def tool_extract_text(file_path: str) -> str:
    """Extract all text content from a PDF file."""
    try:
        if not os.path.isfile(file_path):
            return f"Error: File not found: {file_path}"
        if not file_path.lower().endswith(".pdf"):
            return "Error: File does not appear to be a PDF (expected .pdf extension)"

        try:
            import pdfplumber
        except ImportError:
            return (
                "Error: pdfplumber is not installed. "
                "Install it with: pip install pdfplumber"
            )

        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    pages_text.append(f"--- Page {i} ---\n{text}")
                else:
                    pages_text.append(f"--- Page {i} ---\n(no extractable text)")

        if not pages_text:
            return "No text could be extracted from the PDF."

        total_pages = len(pages_text)
        header = f"Extracted text from {total_pages} page(s) of {os.path.basename(file_path)}:\n\n"
        return header + "\n\n".join(pages_text)
    except Exception as e:
        return f"Error reading PDF: {e}"
