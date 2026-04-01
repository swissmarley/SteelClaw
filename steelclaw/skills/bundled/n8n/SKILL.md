# n8n Integration

Integrate with n8n workflow automation platform to trigger webhooks and manage workflows.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: n8n, workflow, automation

## System Prompt
You can interact with n8n workflow automation. Use the n8n tools to trigger webhooks, list workflows, or execute specific workflows by ID. Credentials must be configured via `steelclaw skills configure n8n`.

## Tools

### trigger_webhook
Trigger an n8n webhook by URL with optional payload data.

**Parameters:**
- `url` (string, required): The webhook URL to trigger
- `payload` (string, optional): JSON payload to send

### list_workflows
List all workflows from the n8n instance.

### execute_workflow
Execute a specific workflow by its ID.

**Parameters:**
- `workflow_id` (string, required): The workflow ID to execute
