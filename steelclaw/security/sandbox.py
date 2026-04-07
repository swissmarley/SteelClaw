"""Sandboxed execution — secure subprocess wrapper and browser automation."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path
from typing import Optional

logger = logging.getLogger("steelclaw.security.sandbox")

# Module-level permission manager — set during app startup
_permission_manager = None
# Module-level sudo manager — set during app startup when sudo is enabled
_sudo_manager = None


def set_permission_manager(pm: object) -> None:
    global _permission_manager
    _permission_manager = pm


def set_sudo_manager(sm: object) -> None:
    """Register the sudo manager for privileged command execution."""
    global _sudo_manager
    _sudo_manager = sm


async def execute_command(
    command: str,
    timeout: int = 30,
    working_directory: str | None = None,
    check_permissions: bool = True,
    sudo: bool = False,
) -> str:
    """Execute a shell command in a sandboxed subprocess.

    Security measures:
    - Permission check via the three-tier model
    - Capability-level category checks (filesystem, network, etc.)
    - Timeout enforcement
    - Working directory validation
    - Output size limits

    When *sudo=True*, the command is routed through the SudoManager which
    requires explicit "YES" confirmation and writes an immutable audit log entry.
    """
    # Route sudo commands through the dedicated sudo manager
    if sudo:
        if _sudo_manager is None:
            return (
                "Error: sudo support is not enabled. "
                "Set agents.security.sudo.enabled = true in config.json."
            )
        return await _sudo_manager.execute_sudo(command, timeout=timeout)

    from steelclaw.security.permissions import PermissionManager

    # Permission check
    if check_permissions and _permission_manager is not None:
        pm: PermissionManager = _permission_manager
        result = await pm.check_command(command)
        if not result.allowed:
            return f"Permission denied: {result.reason}"

    # Validate working directory
    cwd = None
    if working_directory:
        cwd_path = Path(working_directory).resolve()
        if not cwd_path.exists():
            return f"Error: Working directory does not exist: {working_directory}"
        if not cwd_path.is_dir():
            return f"Error: Path is not a directory: {working_directory}"
        cwd = str(cwd_path)

    # Execute with timeout
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=_get_sanitised_env(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return f"Error: Command timed out after {timeout}s"

        output_parts = []
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if stdout_text:
            output_parts.append(stdout_text)
        if stderr_text:
            output_parts.append(f"STDERR:\n{stderr_text}")

        # Truncate very long output
        MAX_OUTPUT = 50_000
        result = "\n".join(output_parts) if output_parts else "(no output)"
        if len(result) > MAX_OUTPUT:
            result = result[:MAX_OUTPUT] + f"\n... (truncated, {len(result)} total chars)"

        if process.returncode != 0:
            result = f"Exit code: {process.returncode}\n{result}"

        return result

    except Exception as e:
        logger.exception("Command execution failed: %s", command)
        return f"Error: {e}"


def _get_sanitised_env() -> dict[str, str]:
    """Return a sanitised copy of the environment, removing sensitive variables."""
    env = dict(os.environ)
    # Remove common secret env vars from the subprocess environment
    sensitive_keys = [
        "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN", "GH_TOKEN",
        "DATABASE_URL", "DATABASE_PASSWORD",
    ]
    for key in sensitive_keys:
        env.pop(key, None)
    return env


async def browse_url(url: str, wait_for: str | None = None) -> str:
    """Open a URL using Playwright and return the page content.

    Requires: pip install 'steelclaw[browser]'
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Error: Playwright not installed. Run: pip install 'steelclaw[browser]'"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=30_000)

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=10_000)

            content = await page.content()
            # Extract text content for LLM consumption
            text = await page.evaluate("document.body.innerText")
            await browser.close()

            # Truncate
            MAX_LEN = 30_000
            if len(text) > MAX_LEN:
                text = text[:MAX_LEN] + "\n... (truncated)"

            return text

    except Exception as e:
        logger.exception("Browser automation failed: %s", url)
        return f"Error browsing URL: {e}"
