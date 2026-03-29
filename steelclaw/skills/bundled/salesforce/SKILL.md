# Salesforce Integration

Query, create, and retrieve records via the Salesforce REST API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: salesforce, crm, soql, records, accounts, leads

## System Prompt
You can interact with Salesforce. Use the Salesforce tools to run SOQL queries, create records, or retrieve record details. Credentials must be configured via `steelclaw skills configure salesforce`.

## Tools

### query
Execute a SOQL query against Salesforce.

**Parameters:**
- `soql` (string, required): The SOQL query string to execute

### create_record
Create a new record in Salesforce.

**Parameters:**
- `object_type` (string, required): The Salesforce object type (e.g. Account, Contact, Lead)
- `data` (string, required): JSON string of field-value pairs for the new record

### get_record
Retrieve a specific record from Salesforce by type and ID.

**Parameters:**
- `object_type` (string, required): The Salesforce object type
- `record_id` (string, required): The Salesforce record ID
