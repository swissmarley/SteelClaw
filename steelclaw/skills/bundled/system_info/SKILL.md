# System Info

Get information about the host system — CPU, memory, disk, network, processes.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: system, cpu, memory, disk, uptime, process, sysinfo, hostname

## System Prompt
You can query the host machine's system status including CPU usage, memory,
disk space, network info, and running processes.

## Tools

### system_status
Get a summary of CPU, memory, disk, and OS information.

### list_processes
List running processes sorted by resource usage.

**Parameters:**
- `sort_by` (string): Sort by "cpu" or "memory" (default: "cpu")
- `limit` (integer): Maximum number of processes to return (default: 15)

### get_environment
Get the values of environment variables.

**Parameters:**
- `names` (string): Comma-separated list of env var names to read (e.g. "PATH,HOME,USER")
