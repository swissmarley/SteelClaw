"""Daemon management — start/stop/restart SteelClaw in background."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console

console = Console()

STEELCLAW_DIR = Path.home() / ".steelclaw"
PID_FILE = STEELCLAW_DIR / "steelclaw.pid"
LOG_DIR = STEELCLAW_DIR / "logs"


def _ensure_dirs() -> None:
    STEELCLAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _read_pid() -> int | None:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is alive
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            PID_FILE.unlink(missing_ok=True)
    return None


def _is_running() -> bool:
    return _read_pid() is not None


def _resolve_python() -> str:
    """Return the best Python executable for the daemon subprocess.

    Prefers the venv Python co-located with this package so that all
    optional dependencies (openviking, chromadb, etc.) are available,
    even when `steelclaw` on PATH was installed into a different Python.
    """
    from steelclaw.paths import PROJECT_ROOT

    # Venv next to the project root (standard `python -m venv venv` layout)
    for candidate in [
        PROJECT_ROOT / "venv" / "bin" / "python3",
        PROJECT_ROOT / "venv" / "bin" / "python",
        PROJECT_ROOT / ".venv" / "bin" / "python3",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return str(candidate)

    # Fall back to the executable that launched this process
    return sys.executable


def start_daemon(host: str | None = None, port: int | None = None) -> None:
    """Start SteelClaw as a background process."""
    _ensure_dirs()

    if _is_running():
        console.print("[yellow]SteelClaw is already running (PID: %d)[/yellow]" % _read_pid())
        return

    log_file = LOG_DIR / "steelclaw.log"

    python = _resolve_python()
    cmd = [python, "-m", "steelclaw", "serve"]
    if host:
        cmd.extend(["--host", host])
    if port:
        cmd.extend(["--port", str(port)])

    from steelclaw.paths import PROJECT_ROOT

    with open(log_file, "a") as log_fh:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
        )

    PID_FILE.write_text(str(proc.pid))
    console.print(f"[green]SteelClaw started (PID: {proc.pid})[/green]")
    console.print(f"Logs: {log_file}")


def stop_daemon() -> None:
    """Stop the background daemon."""
    pid = _read_pid()
    if pid is None:
        console.print("[yellow]SteelClaw is not running[/yellow]")
        return

    console.print(f"Stopping SteelClaw (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait up to 10 seconds for graceful shutdown
        for _ in range(20):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            # Force kill if still running
            console.print("[yellow]Force killing...[/yellow]")
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    PID_FILE.unlink(missing_ok=True)
    console.print("[green]SteelClaw stopped[/green]")


def restart_daemon(host: str | None = None, port: int | None = None) -> None:
    """Stop then start the daemon."""
    if _is_running():
        stop_daemon()
        time.sleep(1)
    start_daemon(host=host, port=port)


def show_status() -> None:
    """Show whether the daemon is running."""
    pid = _read_pid()
    if pid is not None:
        console.print(f"[green]SteelClaw is running (PID: {pid})[/green]")
    else:
        console.print("[red]SteelClaw is not running[/red]")
