# Jira Integration

Search, create, and retrieve issues from Jira Cloud via the REST API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: jira, ticket, sprint, agile

## System Prompt
You can interact with Jira Cloud. Use the Jira tools to search issues, create new issues, or retrieve issue details. Credentials must be configured via `steelclaw skills configure jira`.

## Tools

### search_issues
Search Jira issues using JQL.

**Parameters:**
- `jql` (string, required): JQL query string (e.g. "project = PROJ AND status = Open")
- `max_results` (integer, optional): Maximum results to return (default 20)

### create_issue
Create a new Jira issue.

**Parameters:**
- `project_key` (string, required): The project key (e.g. PROJ)
- `summary` (string, required): Issue summary
- `issue_type` (string, optional): Issue type — Task, Bug, Story (default Task)
- `description` (string, optional): Issue description

### get_issue
Retrieve a Jira issue by key.

**Parameters:**
- `issue_key` (string, required): The issue key (e.g. PROJ-123)
