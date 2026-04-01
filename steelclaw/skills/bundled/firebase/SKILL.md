# Firebase

Interact with Firebase Firestore via the REST API — get, set, and list documents.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: firebase, firestore, google cloud, document database, nosql

## System Prompt
You can use Firebase Firestore. Credentials must be configured via `steelclaw skills configure firebase`.

## Tools

### get_document
Get a single Firestore document.

**Parameters:**
- `collection` (string, required): Collection name
- `document_id` (string, required): Document ID

### set_document
Create or update a Firestore document.

**Parameters:**
- `collection` (string, required): Collection name
- `document_id` (string, required): Document ID
- `data` (string, required): JSON string of the document data

### list_documents
List documents in a Firestore collection.

**Parameters:**
- `collection` (string, required): Collection name
- `page_size` (integer): Max documents to return (default: 20)
