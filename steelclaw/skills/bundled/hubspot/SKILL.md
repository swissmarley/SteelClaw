# HubSpot CRM Integration

List, create, and search contacts via the HubSpot CRM API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: hubspot, crm, contacts, leads, sales

## System Prompt
You can interact with HubSpot CRM. Use the HubSpot tools to list contacts, create new contacts, or search existing contacts. Credentials must be configured via `steelclaw skills configure hubspot`.

## Tools

### list_contacts
List contacts from HubSpot CRM.

**Parameters:**
- `limit` (integer, optional): Maximum number of contacts to return (default 10)

### create_contact
Create a new contact in HubSpot CRM.

**Parameters:**
- `email` (string, required): The contact email address
- `firstname` (string, optional): The contact first name
- `lastname` (string, optional): The contact last name

### search_contacts
Search contacts in HubSpot CRM by query string.

**Parameters:**
- `query` (string, required): Search query to match against contacts
- `limit` (integer, optional): Maximum number of results to return (default 10)
