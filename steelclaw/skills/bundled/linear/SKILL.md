# Linear Integration

List, create, and retrieve issues from Linear via the GraphQL API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: linear, issue tracker, project management

## System Prompt
You can interact with Linear. Use the Linear tools to list issues, create new issues, or get issue details. Credentials must be configured via `steelclaw skills configure linear`.

## Tools

### list_issues
List recent issues from Linear.

**Parameters:**
- `first` (integer, optional): Number of issues to return (default 20)

### create_issue
Create a new issue in Linear.

**Parameters:**
- `team_id` (string, required): The Linear team ID
- `title` (string, required): Issue title
- `description` (string, optional): Issue description in markdown

### get_issue
Get a Linear issue by its identifier.

**Parameters:**
- `issue_id` (string, required): The issue identifier (e.g. ENG-123)
