# Notion Integration

Search, create, and retrieve pages from Notion workspaces via the Notion API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: notion, wiki, pages, knowledge base

## System Prompt
You can interact with Notion workspaces. Use the Notion tools to search pages, create new pages, or retrieve page content. Credentials must be configured via `steelclaw skills configure notion`.

## Tools

### search_pages
Search for pages in a Notion workspace by query string.

**Parameters:**
- `query` (string, required): The search query

### create_page
Create a new page in a Notion database or as a child of another page.

**Parameters:**
- `parent_id` (string, required): The parent page or database ID
- `title` (string, required): The page title
- `content` (string, optional): Plain text content for the page body

### get_page
Retrieve a Notion page by its ID.

**Parameters:**
- `page_id` (string, required): The Notion page ID
