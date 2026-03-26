"""Shell skill — tool executors for command execution."""

from __future__ import annotations


async def tool_run_command(
    command: str,
    timeout: int = 30,
    working_directory: str | None = None,
) -> str:
    """Execute a shell command. Delegates to the security sandbox."""
    # Import here to avoid circular imports
    from steelclaw.security.sandbox import execute_command

    return await execute_command(
        command=command,
        timeout=timeout,
        working_directory=working_directory,
    )
