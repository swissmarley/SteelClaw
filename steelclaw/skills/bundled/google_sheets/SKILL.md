# Google Sheets Integration

Read, write, and list sheets from Google Sheets spreadsheets.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: google sheets, spreadsheet, gsheets, sheets

## System Prompt
You can interact with Google Sheets. Use the Google Sheets tools to read ranges, write data, or list sheets in a spreadsheet. Credentials must be configured via `steelclaw skills configure google_sheets`.

## Tools

### read_range
Read data from a range in a Google Sheets spreadsheet.

**Parameters:**
- `spreadsheet_id` (string, required): The spreadsheet ID
- `range` (string, required): The A1 notation range (e.g. Sheet1!A1:D10)

### write_range
Write data to a range in a Google Sheets spreadsheet.

**Parameters:**
- `spreadsheet_id` (string, required): The spreadsheet ID
- `range` (string, required): The A1 notation range
- `values` (string, required): JSON array of arrays with the values to write

### list_sheets
List all sheets in a spreadsheet.

**Parameters:**
- `spreadsheet_id` (string, required): The spreadsheet ID
