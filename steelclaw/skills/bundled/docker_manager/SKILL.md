# Docker Manager

Manage Docker containers from the command line.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: docker, container, start container, stop container, list containers

## System Prompt
You can manage Docker containers using list_containers, start_container, and stop_container.
These tools call the Docker CLI directly via subprocess. Docker must be installed and
the daemon must be running.

## Tools

### list_containers
List all Docker containers (running and stopped).

### start_container
Start a stopped Docker container.

**Parameters:**
- `name` (string, required): Container name or ID to start

### stop_container
Stop a running Docker container.

**Parameters:**
- `name` (string, required): Container name or ID to stop
