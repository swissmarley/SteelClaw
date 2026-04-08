"""Sudo command execution with explicit user confirmation and immutable audit logging.

Design principles:
- Master toggle disabled by default (zero auto-approval)
- Requires explicit approval through the interactive permission system
- Every approval or denial is appended to an append-only audit log
- An optional whitelist skips the interactive prompt for pre-approved executables
- Commands are parsed with shlex and run via exec (not shell) to prevent injection
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import shlex
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from steelclaw.security.permission_models import (
    PermissionDecision,
    PermissionRequest,
)

if TYPE_CHECKING:
    from steelclaw.security.broadcaster import PermissionBroadcaster

logger = logging.getLogger("steelclaw.security.sudo")

# Maximum output size returned to the caller (matches sandbox.py)
_MAX_OUTPUT = 50_000

# Callback type: async fn(prompt_text: str) -> str
SudoConfirmCallback = Callable[[str], Coroutine[Any, Any, str]]


def _get_sanitised_env() -> dict[str, str]:
    """Return a copy of the environment with sensitive variables removed.

    Mirrors the sanitisation in steelclaw.security.sandbox to prevent
    credentials leaking into the sudo subprocess environment.
    """
    env = dict(os.environ)
    sensitive = [
        "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN", "GH_TOKEN",
        "DATABASE_URL", "DATABASE_PASSWORD",
    ]
    for key in sensitive:
        env.pop(key, None)
    return env


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
        self._broadcaster: "PermissionBroadcaster | None" = None
        # Per-session sudo password cache: session_id → (password, expires_at)
        self._password_cache: dict[str, tuple[str, float]] = {}

    def set_confirm_callback(self, callback: SudoConfirmCallback) -> None:
        """Register the async callback used to prompt the user for confirmation.

        Deprecated: Use set_broadcaster for interactive permissions.
        """
        self._confirm_callback = callback

    def set_broadcaster(self, broadcaster: "PermissionBroadcaster") -> None:
        """Set the broadcaster for interactive sudo confirmations."""
        self._broadcaster = broadcaster

    def _is_whitelisted(self, command: str) -> bool:
        """Return True if the command matches any whitelist glob pattern."""
        cmd_lower = command.lower().strip()
        for pattern in self._config.whitelist:
            if fnmatch.fnmatch(cmd_lower, pattern.lower()):
                return True
        return False

    async def _write_audit(self, status: str, command: str) -> None:
        """Append an immutable audit entry to the log file."""
        import json
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "command": command,
        }
        content = json.dumps(entry) + "\n"

        # Use asyncio.to_thread for non-blocking file I/O
        def _write():
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(content)

        await asyncio.to_thread(_write)

    async def execute_sudo(
        self,
        command: str,
        timeout: int | None = None,
        session_id: str | None = None,
        platform: str | None = None,
        platform_chat_id: str | None = None,
    ) -> str:
        """Execute *command* with sudo after mandatory user confirmation.

        Returns the command output on success, or a descriptive error string.

        Confirmation rules:
        - Whitelisted commands (glob match) are approved automatically.
        - All other commands require interactive approval through the broadcaster.
        - Uses the same permission system as shell commands.
        """
        if not self._config.enabled:
            return (
                "Error: sudo support is not enabled. "
                "Set agents.security.sudo.enabled = true in config.json to enable it."
            )

        # exec_timeout: how long the subprocess itself may run
        exec_timeout = timeout or 30
        # ui_timeout: how long to wait for the user to interact with popups.
        # Use the broadcaster's configured timeout (= security.permission_timeout,
        # typically 300 s) so users are not rushed by the short command timeout.
        ui_timeout = (self._broadcaster._timeout if self._broadcaster else None) or 300

        # Check whitelist first (no prompt needed for pre-approved patterns)
        if self._is_whitelisted(command):
            logger.info("Sudo command auto-approved via whitelist: %s", command[:80])
            self._write_audit("AUTO-APPROVED (whitelist)", command)
            return await self._run_sudo(command, exec_timeout)

        # Interactive confirmation via broadcaster
        if self._broadcaster and session_id and platform and platform_chat_id:
            request = PermissionRequest.create(
                command=f"sudo {command}",
                tool_name="sudo",
                session_id=session_id,
                platform=platform,
                platform_chat_id=platform_chat_id,
                timeout_seconds=ui_timeout,
                context="Privileged command execution requires approval",
            )
            try:
                decision = await self._broadcaster.broadcast_request(request)
                if decision in (PermissionDecision.APPROVE_ONCE, PermissionDecision.APPROVE_SESSION):
                    # Obtain sudo password (from cache or via popup)
                    password = await self._get_sudo_password(
                        session_id=session_id,
                        command=command,
                        timeout=ui_timeout,
                    )
                    if password is None:
                        self._write_audit("DENIED (no password)", command)
                        return "sudo command cancelled: no password provided"
                    self._write_audit("APPROVED", command)
                    return await self._run_sudo(command, exec_timeout, password=password)
                else:
                    self._write_audit("DENIED (user)", command)
                    return "sudo command denied by user"
            except asyncio.TimeoutError:
                self._write_audit("DENIED (timeout)", command)
                logger.warning("Sudo confirmation timed out for: %s", command[:80])
                return f"Error: sudo confirmation timed out after {ui_timeout}s"
            except Exception as e:
                logger.exception("Sudo confirmation error: %s", e)
                self._write_audit("ERROR", command)
                return f"Error: sudo confirmation failed: {e}"

        self._write_audit("DENIED (no approval channel)", command)
        return (
            "Error: sudo confirmation channel is not available. "
            "Cannot execute privileged commands without user approval."
        )

    async def _get_sudo_password(
        self,
        session_id: str,
        command: str,
        timeout: int,
    ) -> Optional[str]:
        """Return a valid sudo password, using the session cache when still fresh.

        If the cached password has expired (or was never set), requests a new
        one from the user via the broadcaster's sudo password popup.
        On success, stores the new password in the cache for *session_timeout*
        seconds (from settings).
        """
        # Check in-memory cache
        cached = self._password_cache.get(session_id)
        if cached:
            password, expires_at = cached
            if time.monotonic() < expires_at:
                logger.debug("Using cached sudo password for session %s", session_id)
                return password
            # Expired — remove stale entry
            del self._password_cache[session_id]

        if not self._broadcaster:
            return None

        request_id = str(uuid.uuid4())
        password = await self._broadcaster.request_sudo_password(
            request_id=request_id,
            command=f"sudo {command}",
            timeout_seconds=timeout,
            context="Enter your sudo password to authenticate",
        )

        if password:
            session_timeout = getattr(self._config, "session_timeout", 300)
            self._password_cache[session_id] = (
                password,
                time.monotonic() + session_timeout,
            )
            logger.info(
                "Sudo password cached for session %s (expires in %ds)",
                session_id,
                session_timeout,
            )

        return password

    async def _run_sudo(self, command: str, timeout: int, password: Optional[str] = None) -> str:
        """Run a sudo command using exec (not shell) to prevent injection.

        The command is parsed with ``shlex.split()`` and passed as an argument
        list to ``create_subprocess_exec``.  This prevents shell metacharacters
        in *command* (e.g. ``;``, ``&&``, ``|``) from being interpreted by a
        shell.  Environment is sanitised to avoid credential leakage.
        When *password* is provided the ``-S`` flag is used so sudo reads the
        password from stdin — no TTY is required in that case.
        Output is truncated at ``_MAX_OUTPUT`` characters to prevent memory
        exhaustion from verbose commands.
        """
        try:
            args = shlex.split(command)
        except ValueError as e:
            return f"Error: Could not parse sudo command: {e}"

        sudo_args = ["sudo"]
        stdin_data: Optional[bytes] = None
        if password is not None:
            sudo_args.extend(["-S", "-p", ""])  # -S reads from stdin, -p "" suppresses prompt
            stdin_data = (password + "\n").encode()

        try:
            process = await asyncio.create_subprocess_exec(
                *sudo_args,
                *args,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_get_sanitised_env(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_data),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return f"Error: sudo command timed out after {timeout}s"

            output_parts = []
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if stdout_text:
                output_parts.append(stdout_text)
            if stderr_text:
                output_parts.append(f"STDERR:\n{stderr_text}")

            result = "\n".join(output_parts) if output_parts else "(no output)"
            if len(result) > _MAX_OUTPUT:
                result = result[:_MAX_OUTPUT] + f"\n... (truncated, {len(result)} total chars)"

            if process.returncode != 0:
                result = f"Exit code: {process.returncode}\n{result}"

            return result

        except FileNotFoundError:
            return "Error: sudo command not found. Ensure sudo is installed."
        except Exception as e:
            logger.exception("Sudo execution failed: %s", e)
            return f"Error: {e}"