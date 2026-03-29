# System Monitor Extended

Extended system monitoring with process listing, disk usage, and system statistics.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: system stats, processes, disk usage, memory, cpu, system monitor, top, df

## System Prompt
You can monitor system resources using extended tools. Get CPU, memory, and load stats
with get_system_stats; list top processes with get_process_list; and check disk usage
with get_disk_usage. Uses psutil if available, falls back to system commands.

## Tools

### get_system_stats
Get current CPU, memory, and system load statistics.

### get_process_list
List the top processes by CPU or memory usage.

**Parameters:**
- `count` (integer, optional): Number of top processes to show (default: 10)

### get_disk_usage
Get disk usage information for all mounted filesystems.
