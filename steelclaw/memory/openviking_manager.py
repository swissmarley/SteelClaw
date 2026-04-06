"""OpenViking server subprocess lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import socket
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

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._process: asyncio.subprocess.Process | None = None
        self._healthy = False

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

        try:
            logger.info("Starting OpenViking server on port %d...", port)
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for server to become healthy
            self._healthy = await self._health_check(url, retries=10, delay=0.5)
            if self._healthy:
                logger.info("OpenViking server started successfully (PID: %d)", self._process.pid)
                return True
            else:
                logger.error("OpenViking server failed to start within timeout")
                await self.stop()
                return False

        except FileNotFoundError:
            logger.error(
                "openviking-server not found — install with: pip install openviking"
            )
            return False
        except Exception as exc:
            logger.error("Failed to start OpenViking server: %s", exc)
            await self.stop()
            return False

    async def stop(self) -> None:
        """Stop the OpenViking server subprocess gracefully."""
        if self._process is None:
            return

        if self._process.returncode is not None:
            self._process = None
            self._healthy = False
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