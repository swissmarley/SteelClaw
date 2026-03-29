# GitHub Integration

List repositories, create issues, and list issues via the GitHub API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: github, repo, repository, issues

## System Prompt
You can interact with GitHub repositories. Use the GitHub tools to list repos, create issues, or list issues. Credentials must be configured via `steelclaw skills configure github_skill`.

## Tools

### list_repos
List repositories for the authenticated user.

**Parameters:**
- `sort` (string, optional): Sort field — created, updated, pushed, full_name (default updated)

### create_issue
Create a new issue in a GitHub repository.

**Parameters:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `title` (string, required): Issue title
- `body` (string, optional): Issue body/description

### list_issues
List issues for a GitHub repository.

**Parameters:**
- `owner` (string, required): Repository owner
- `repo` (string, required): Repository name
- `state` (string, optional): Filter by state — open, closed, all (default open)
