"""Sudo command execution with explicit user confirmation and immutable audit logging.

Design principles:
- Master toggle disabled by default (zero auto-approval)
- Requires the user to type the literal string "YES" (not "yes", not "y")
- Every approval or denial is appended to an append-only audit log
- An optional command whitelist skips the interactive prompt for pre-approved patterns
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine

logger = logging.getLogger("steelclaw.security.sudo")

# Callback type: async fn(prompt_text: str) -> str
SudoConfirmCallback = Callable[[str], Coroutine[Any, Any, str]]


class SudoManager:
    """Manages privileged command execution with strict confirmation requirements."""

    def __init__(self, sudo_config) -> None:
        """
        Args:
            sudo_config: SudoSettings instance from steelclaw.settings.
        """
        self._config = sudo_config
        self._audit_path = Path(sudo_config.audit_log).expanduser().resolve()
        self._confirm_callback: SudoConfirmCallback | None = None

    def set_confirm_callback(self, callback: SudoConfirmCallback) -> None:
        """Register the async callback used to prompt the user for confirmation."""
        self._confirm_callback = callback

    async def execute_sudo(
        self,
        command: str,
        timeout: int | None = None,
    ) -> str:
        """Execute *command* with sudo after mandatory user confirmation.

        Returns the command output on success, or a descriptive error string.

        Confirmation rules:
        - Whitelisted commands (glob match) are approved automatically.
        - All other commands require the user to reply with the exact string
          "YES" (uppercase, no trailing spaces) within *session_timeout* seconds.
        - Any other response — including "yes", "y", "ok" — is treated as a denial.
        """
        if not self._config.enabled:
            return (
                "Error: sudo support is not enabled. "
                "Set agents.security.sudo.enabled = true in config.json to enable it."
            )

        timeout = timeout or self._config.session_timeout

        # Check whitelist first (no prompt needed for pre-approved patterns)
        if self._is_whitelisted(command):
            logger.info("Sudo command auto-approved via whitelist: %s", command[:80])
            self._write_audit("AUTO-APPROVED (whitelist)", command)
            return await self._run_sudo(command, timeout)

        # Interactive confirmation required
        if self._confirm_callback is None:
            self._write_audit("DENIED (no callback)", command)
            return (
                "Error: sudo confirmation channel is not available. "
                "Cannot execute privileged commands without user approval."
            )

        prompt = (
            f"\u26a0\ufe0f  **Sudo command requested**\n"
            f"`sudo {command}`\n\n"
            f"Type **YES** (exactly, uppercase) to confirm, or anything else to cancel:"
        )

        try:
            response = await asyncio.wait_for(
                self._confirm_callback(prompt),
                timeout=float(timeout),
            )
        except asyncio.TimeoutError:
            self._write_audit("DENIED (timeout)", command)
            logger.warning("Sudo confirmation timed out for: %s", command[:80])
            return f"Error: sudo confirmation timed out after {timeout}s"

        # Strict "YES" check — no case folding, no trimming beyond stripping newlines
        confirmed = isinstance(response, str) and response.strip() == "YES"

        if not confirmed:
            self._write_audit("DENIED (user)", command)
            logger.info("User denied sudo command: %s", command[:80])
            return "sudo command denied: confirmation required (type YES to approve)"

        self._write_audit("APPROVED", command)
        return await self._run_sudo(command, timeout)

    async def _run_sudo(self, command: str, timeout: int) -> str:
        """Actually run the command prefixed with sudo."""
        try:
            full_cmd = f"sudo {command}"
            process = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=float(timeout),
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return f"Error: sudo command timed out after {timeout}s"

            parts = []
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if stdout_text:
                parts.append(stdout_text)
            if stderr_text:
                parts.append(f"STDERR:\n{stderr_text}")

            output = "\n".join(parts) if parts else "(no output)"
            if process.returncode != 0:
                output = f"Exit code: {process.returncode}\n{output}"

            logger.info("Sudo command completed (rc=%s): %s", process.returncode, command[:80])
            return output

        except Exception as exc:
            logger.exception("Sudo execution failed: %s", command)
            return f"Error executing sudo command: {exc}"

    def _is_whitelisted(self, command: str) -> bool:
        """Return True if the command matches any whitelist glob pattern."""
        for pattern in self._config.whitelist:
            if fnmatch.fnmatch(command, pattern) or fnmatch.fnmatch(command.lower(), pattern.lower()):
                return True
        return False

    def _write_audit(self, status: str, command: str) -> None:
        """Append an immutable audit entry to the audit log file.

        The log is opened in append mode ('a') — entries are never deleted.
        """
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = f"[{timestamp}] [{status}] cmd={command!r}\n"
            with self._audit_path.open("a", encoding="utf-8") as fh:
                fh.write(entry)
        except Exception as exc:
            logger.error("Failed to write sudo audit log: %s", exc)
