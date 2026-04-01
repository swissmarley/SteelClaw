# Airtable Integration

List, create, and retrieve records from Airtable bases.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: airtable, spreadsheet, database, records

## System Prompt
You can interact with Airtable bases. Use the Airtable tools to list records, create new records, or get specific records. Credentials must be configured via `steelclaw skills configure airtable`.

## Tools

### list_records
List records from an Airtable table.

**Parameters:**
- `max_records` (integer, optional): Maximum number of records to return (default 20)

### create_record
Create a new record in an Airtable table.

**Parameters:**
- `fields` (string, required): JSON object of field names and values

### get_record
Retrieve a specific record by ID.

**Parameters:**
- `record_id` (string, required): The Airtable record ID
