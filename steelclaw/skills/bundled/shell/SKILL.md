# Shell

Execute shell commands on the host machine.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: run, execute, shell, terminal, command

## System Prompt
You can execute shell commands on the user's machine using the run_command tool.
Always explain what a command does before running it.
Never run destructive commands without explicit user confirmation.

## Tools

### run_command
Execute a shell command on the host machine and return its output.

**Parameters:**
- `command` (string, required): The shell command to execute
- `timeout` (integer): Maximum execution time in seconds (default: 30)
- `working_directory` (string): Directory to run the command in
