# CSV Analyst

Parse, filter, and summarize CSV files.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: csv, spreadsheet, parse csv, analyze csv, summarize csv, tabular data

## System Prompt
You can read and analyze CSV files. Use read_csv to view rows (with optional row limit)
and summarize_csv to get column statistics including types, counts, and sample values.
Uses Python stdlib — no extra dependencies required.

## Tools

### read_csv
Read and display rows from a CSV file in tabular format.

**Parameters:**
- `file_path` (string, required): Absolute path to the CSV file
- `max_rows` (integer, optional): Maximum number of rows to return (default: 100)

### summarize_csv
Generate a summary of a CSV file including column names, types, row count, and basic statistics.

**Parameters:**
- `file_path` (string, required): Absolute path to the CSV file
