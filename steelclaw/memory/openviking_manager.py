"""OpenViking server subprocess lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import socket
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from steelclaw.settings import MemorySettings

logger = logging.getLogger("steelclaw.memory")


class OpenVikingManager:
    """Manages OpenViking server subprocess lifecycle.

    Handles:
    - Starting OpenViking as a subprocess
    - Health check with retries
    - Graceful shutdown
    - Port conflict detection
    """

    # Auto-restart configuration — OpenViking is known to segfault on
    # Python 3.14 during async idle tasks (EXC_BAD_ACCESS in
    # PyUnicode_AsUTF8AndSize).  The watchdog restarts the subprocess up
    # to _MAX_RESTARTS times within _RESTART_WINDOW_S seconds before
    # giving up.  Counter resets after a process stays alive longer than
    # the window.
    _MAX_RESTARTS = 3
    _RESTART_WINDOW_S = 300.0  # 5 minutes
    _WATCHDOG_POLL_S = 5.0
    _RESTART_BACKOFF_S = 2.0

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._process: asyncio.subprocess.Process | None = None
        self._healthy = False
        self._log_fh = None
        self._watchdog_task: asyncio.Task | None = None
        self._shutting_down = False
        self._restart_count = 0
        self._first_restart_at: float | None = None

    @property
    def is_running(self) -> bool:
        """Check if the subprocess is running."""
        return self._process is not None and self._process.returncode is None

    @property
    def is_healthy(self) -> bool:
        """Check if server is responding to health checks."""
        return self._healthy

    async def _is_port_in_use(self, port: int, host: str = "localhost") -> bool:
        """Check if a port is already in use."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=1.0,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            return False

    async def _health_check(self, url: str, retries: int = 5, delay: float = 1.0) -> bool:
        """Ping the OpenViking server health endpoint with retries."""
        import httpx

        health_url = f"{url.rstrip('/')}/health"
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(health_url)
                    if resp.status_code == 200:
                        logger.info(
                            "OpenViking health check passed (attempt %d/%d)",
                            attempt + 1,
                            retries,
                        )
                        return True
            except Exception as exc:
                logger.debug(
                    "OpenViking health check failed (attempt %d/%d): %s",
                    attempt + 1,
                    retries,
                    exc,
                )
                await asyncio.sleep(delay)

        logger.warning("OpenViking health check failed after %d retries", retries)
        return False

    async def start(self) -> bool:
        """Start the OpenViking server subprocess.

        Returns:
            True if server started successfully, False otherwise.
        """
        if not self._settings.openviking_auto_start:
            logger.info("OpenViking auto-start disabled via config")
            return False

        self._shutting_down = False
        ok = await self._launch_subprocess()
        if ok:
            # Spawn watchdog to auto-restart on crash
            self._watchdog_task = asyncio.create_task(self._watchdog())
        return ok

    async def _launch_subprocess(self) -> bool:
        """Launch (or re-launch) the OpenViking subprocess once.

        Does NOT spawn the watchdog — that's the responsibility of
        :meth:`start`.  This method is also called from the watchdog
        itself to restart after a crash.
        """
        port = self._settings.openviking_port
        url = self._settings.openviking_server_url

        # Check if port is already in use
        if await self._is_port_in_use(port):
            # Check if it's an OpenViking server already running
            if await self._health_check(url, retries=1):
                logger.info("OpenViking server already running on port %d", port)
                self._healthy = True
                return True
            else:
                logger.warning(
                    "Port %d is in use but not by OpenViking — cannot start server",
                    port,
                )
                return False

        # Start the subprocess
        cmd = [
            "openviking-server",
            "--port", str(port),
            "--host", "127.0.0.1",
        ]

        # Redirect stdout/stderr to a log file.  If we used PIPE without
        # draining, the buffers (typically ~64KB) would fill and the
        # OpenViking process would block on writes, effectively freezing
        # the server.
        log_dir = Path.home() / ".steelclaw" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "openviking.log"
        self._log_fh = open(log_path, "ab", buffering=0)

        try:
            logger.info("Starting OpenViking server on port %d...", port)
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=self._log_fh,
                stderr=self._log_fh,
            )

            # Wait for server to become healthy.  OpenViking can take
            # 5–10 seconds to import on first run (Python 3.14, large
            # dependency tree), so give it a generous window.
            self._healthy = await self._health_check(url, retries=30, delay=1.0)
            if self._healthy:
                logger.info("OpenViking server started successfully (PID: %d)", self._process.pid)
                return True
            else:
                logger.error("OpenViking server failed to start within timeout")
                await self._terminate_subprocess()
                return False

        except FileNotFoundError:
            logger.error(
                "openviking-server not found — install with: pip install openviking"
            )
            if self._log_fh is not None:
                self._log_fh.close()
                self._log_fh = None
            return False
        except Exception as exc:
            logger.error("Failed to start OpenViking server: %s", exc)
            await self._terminate_subprocess()
            return False

    async def _watchdog(self) -> None:
        """Monitor the subprocess and auto-restart on crash.

        OpenViking has a known Python 3.14 incompatibility that causes
        it to segfault during async idle callbacks (EXC_BAD_ACCESS in
        PyUnicode_AsUTF8AndSize).  Rather than leaving the memory
        subsystem disabled until the next SteelClaw restart, we detect
        the crash and respawn the subprocess in-place, up to
        ``_MAX_RESTARTS`` times within ``_RESTART_WINDOW_S`` seconds.
        """
        import time

        while not self._shutting_down:
            try:
                await asyncio.sleep(self._WATCHDOG_POLL_S)
            except asyncio.CancelledError:
                return

            if self._shutting_down:
                return

            proc = self._process
            if proc is None:
                # Nothing to watch — likely stopped.
                return

            rc = proc.returncode
            if rc is None:
                continue  # still running, all good

            # Subprocess has exited — figure out if we should restart.
            logger.warning(
                "OpenViking subprocess exited unexpectedly (PID=%d, code=%s)",
                proc.pid,
                rc,
            )
            self._healthy = False

            # Clean up the dead process and its log handle
            self._process = None
            if self._log_fh is not None:
                try:
                    self._log_fh.close()
                except Exception:
                    pass
                self._log_fh = None

            # Rate-limit restarts within the restart window
            now = time.monotonic()
            if (
                self._first_restart_at is None
                or now - self._first_restart_at > self._RESTART_WINDOW_S
            ):
                # Outside window (or first restart) — reset counter
                self._first_restart_at = now
                self._restart_count = 0

            if self._restart_count >= self._MAX_RESTARTS:
                logger.error(
                    "OpenViking crashed %d times in %.0fs — giving up auto-restart",
                    self._restart_count,
                    self._RESTART_WINDOW_S,
                )
                return

            self._restart_count += 1
            logger.info(
                "Auto-restarting OpenViking (attempt %d/%d)...",
                self._restart_count,
                self._MAX_RESTARTS,
            )

            try:
                await asyncio.sleep(self._RESTART_BACKOFF_S)
            except asyncio.CancelledError:
                return

            try:
                ok = await self._launch_subprocess()
            except Exception as exc:
                logger.error("OpenViking auto-restart raised: %s", exc)
                ok = False

            if ok:
                logger.info("OpenViking auto-restart succeeded")
            else:
                logger.error("OpenViking auto-restart failed")
                # Fall through and keep watching — the loop will retry
                # on the next iteration if the process is still None.

    async def _terminate_subprocess(self) -> None:
        """Terminate the subprocess without cancelling the watchdog.

        Used internally (e.g. from within the watchdog) where stop()
        would recursively cancel our own task.
        """
        if self._process is None:
            return
        if self._process.returncode is None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
        self._process = None
        self._healthy = False
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None

    async def stop(self) -> None:
        """Stop the OpenViking server subprocess gracefully."""
        # Signal watchdog to exit before touching the subprocess so it
        # doesn't mistake our intentional shutdown for a crash.
        self._shutting_down = True
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        self._watchdog_task = None

        if self._process is None:
            return

        if self._process.returncode is not None:
            self._process = None
            self._healthy = False
            if self._log_fh is not None:
                try:
                    self._log_fh.close()
                except Exception:
                    pass
                self._log_fh = None
            return

        logger.info("Stopping OpenViking server (PID: %d)...", self._process.pid)

        try:
            # Try graceful shutdown first
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
                logger.info("OpenViking server stopped gracefully")
            except asyncio.TimeoutError:
                # Force kill if it doesn't respond
                logger.warning("OpenViking server didn't stop gracefully, forcing...")
                self._process.kill()
                await self._process.wait()
                logger.info("OpenViking server killed")
        except ProcessLookupError:
            pass  # Process already gone
        finally:
            self._process = None
            self._healthy = False
            if self._log_fh is not None:
                try:
                    self._log_fh.close()
                except Exception:
                    pass
                self._log_fh = None

    async def get_status(self) -> dict:
        """Get current server status."""
        import httpx

        status = {
            "running": self.is_running,
            "healthy": self._healthy,
            "port": self._settings.openviking_port,
            "url": self._settings.openviking_server_url,
            "workspace": self._settings.openviking_workspace,
        }

        # Try to get more info from the server
        if self._healthy:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{self._settings.openviking_server_url.rstrip('/')}/stats")
                    if resp.status_code == 200:
                        status["stats"] = resp.json()
            except Exception:
                pass

        return status

    async def __aenter__(self) -> "OpenVikingManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
