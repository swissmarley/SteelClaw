"""Docker Manager skill — manage Docker containers via CLI."""

from __future__ import annotations

import shutil
import subprocess


def _docker_available() -> str | None:
    """Check if Docker CLI is available. Returns error string or None."""
    if not shutil.which("docker"):
        return "Error: Docker CLI not found. Please install Docker first."
    return None


def _run_docker(args: list[str]) -> str:
    """Run a docker command and return output."""
    result = subprocess.run(
        ["docker"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"Error (exit {result.returncode}):\n{result.stderr.strip()}"
    return result.stdout.strip()


async def tool_list_containers() -> str:
    """List all Docker containers (running and stopped)."""
    try:
        err = _docker_available()
        if err:
            return err

        output = _run_docker([
            "ps", "-a",
            "--format", "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
        ])
        if not output:
            return "No containers found."
        return output
    except Exception as e:
        return f"Error listing containers: {e}"


async def tool_start_container(name: str) -> str:
    """Start a stopped Docker container."""
    try:
        err = _docker_available()
        if err:
            return err

        output = _run_docker(["start", name])
        if output.startswith("Error"):
            return output
        return f"Container '{name}' started successfully."
    except Exception as e:
        return f"Error starting container: {e}"


async def tool_stop_container(name: str) -> str:
    """Stop a running Docker container."""
    try:
        err = _docker_available()
        if err:
            return err

        output = _run_docker(["stop", name])
        if output.startswith("Error"):
            return output
        return f"Container '{name}' stopped successfully."
    except Exception as e:
        return f"Error stopping container: {e}"
