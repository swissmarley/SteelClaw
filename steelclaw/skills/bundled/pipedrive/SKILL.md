# Pipedrive Integration

List, create, and retrieve deals via the Pipedrive API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: pipedrive, deals, crm, sales, pipeline

## System Prompt
You can interact with Pipedrive. Use the Pipedrive tools to list deals, create new deals, or retrieve deal details. Credentials must be configured via `steelclaw skills configure pipedrive`.

## Tools

### list_deals
List deals from Pipedrive.

**Parameters:**
- `limit` (integer, optional): Maximum number of deals to return (default 10)

### create_deal
Create a new deal in Pipedrive.

**Parameters:**
- `title` (string, required): The deal title
- `value` (number, optional): The deal value (default 0)
- `currency` (string, optional): Currency code (default USD)
- `person_id` (integer, optional): Associated person ID

### get_deal
Retrieve a specific deal from Pipedrive by ID.

**Parameters:**
- `deal_id` (integer, required): The Pipedrive deal ID
