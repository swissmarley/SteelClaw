# Code Runner

Execute Python, JavaScript, or Bash code in a sandboxed subprocess with a 30-second timeout.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: run code, execute, python, javascript, bash, script, eval code

## System Prompt
You can execute code snippets in Python, JavaScript, or Bash using the run_code tool.
Code runs in a subprocess with a 30-second timeout. Both stdout and stderr are captured.
Use this when the user wants to test code, run scripts, or execute shell commands.

## Tools

### run_code
Execute code in a subprocess and return the output.

**Parameters:**
- `code` (string, required): The source code to execute
- `language` (string, required): Language to run — one of: python, javascript, bash
