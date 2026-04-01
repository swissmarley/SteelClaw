# Supabase

Interact with Supabase databases via the REST API — query, insert, and delete rows.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: supabase, database, postgres, backend, baas

## System Prompt
You can use Supabase. Credentials must be configured via `steelclaw skills configure supabase`.

## Tools

### query_table
Query rows from a Supabase table.

**Parameters:**
- `table` (string, required): Table name
- `select` (string): Columns to select (default: "*")
- `filters` (string): PostgREST filter string (e.g. "id=eq.5")
- `limit` (integer): Max rows to return (default: 50)

### insert_row
Insert a row into a Supabase table.

**Parameters:**
- `table` (string, required): Table name
- `data` (string, required): JSON string of the row data

### delete_row
Delete rows from a Supabase table.

**Parameters:**
- `table` (string, required): Table name
- `filters` (string, required): PostgREST filter string (e.g. "id=eq.5")
