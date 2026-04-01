# GitLab Integration

List projects, create issues, and list pipelines via the GitLab API.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: gitlab, project, pipeline, merge request

## System Prompt
You can interact with GitLab. Use the GitLab tools to list projects, create issues, or list pipelines. Credentials must be configured via `steelclaw skills configure gitlab`.

## Tools

### list_projects
List projects accessible to the authenticated user.

**Parameters:**
- `search` (string, optional): Search query to filter projects

### create_issue
Create a new issue in a GitLab project.

**Parameters:**
- `project_id` (string, required): The project ID or URL-encoded path
- `title` (string, required): Issue title
- `description` (string, optional): Issue description

### list_pipelines
List pipelines for a GitLab project.

**Parameters:**
- `project_id` (string, required): The project ID or URL-encoded path
- `status` (string, optional): Filter by status — running, pending, success, failed
