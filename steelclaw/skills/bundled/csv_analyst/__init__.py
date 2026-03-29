"""CSV Analyst skill — parse, filter, and summarize CSV files."""

from __future__ import annotations

import csv
import os
from collections import defaultdict


async def tool_read_csv(file_path: str, max_rows: int = 100) -> str:
    """Read and display rows from a CSV file in tabular format."""
    try:
        if not os.path.isfile(file_path):
            return f"Error: File not found: {file_path}"

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = []
            for i, row in enumerate(reader):
                rows.append(row)
                if i >= max_rows:  # header + max_rows data rows
                    break

        if not rows:
            return "CSV file is empty."

        # Calculate column widths
        col_widths = [0] * len(rows[0])
        for row in rows:
            for j, cell in enumerate(row):
                if j < len(col_widths):
                    col_widths[j] = max(col_widths[j], len(cell))

        # Format table
        def format_row(row):
            parts = []
            for j, cell in enumerate(row):
                width = col_widths[j] if j < len(col_widths) else len(cell)
                parts.append(cell.ljust(width))
            return " | ".join(parts)

        lines = [format_row(rows[0])]
        lines.append("-+-".join("-" * w for w in col_widths))
        for row in rows[1:]:
            lines.append(format_row(row))

        total_info = f"\nShowing {len(rows) - 1} row(s)"
        if len(rows) - 1 >= max_rows:
            total_info += f" (limited to {max_rows})"

        return "\n".join(lines) + total_info
    except Exception as e:
        return f"Error reading CSV: {e}"


async def tool_summarize_csv(file_path: str) -> str:
    """Generate a summary of a CSV file."""
    try:
        if not os.path.isfile(file_path):
            return f"Error: File not found: {file_path}"

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return "CSV file is empty or has no headers."

            col_data: dict[int, list[str]] = defaultdict(list)
            row_count = 0
            for row in reader:
                row_count += 1
                for j, cell in enumerate(row):
                    col_data[j].append(cell.strip())

        lines = [
            f"File: {os.path.basename(file_path)}",
            f"Rows: {row_count}",
            f"Columns: {len(headers)}",
            "",
            "Column Details:",
            "-" * 60,
        ]

        for j, header in enumerate(headers):
            values = col_data.get(j, [])
            non_empty = [v for v in values if v]
            empty_count = len(values) - len(non_empty)

            # Detect numeric
            numeric_vals = []
            for v in non_empty:
                try:
                    numeric_vals.append(float(v))
                except ValueError:
                    pass

            unique_count = len(set(non_empty))
            lines.append(f"\n  {header}:")
            lines.append(f"    Non-empty: {len(non_empty)}, Empty: {empty_count}, Unique: {unique_count}")

            if numeric_vals and len(numeric_vals) == len(non_empty):
                lines.append(f"    Type: numeric")
                lines.append(f"    Min: {min(numeric_vals)}, Max: {max(numeric_vals)}, "
                             f"Mean: {sum(numeric_vals) / len(numeric_vals):.2f}")
            else:
                lines.append(f"    Type: text")
                sample = non_empty[:5]
                lines.append(f"    Sample: {sample}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error summarizing CSV: {e}"
