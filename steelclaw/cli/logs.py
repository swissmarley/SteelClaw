"""CLI log viewer for daemon mode."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console

console = Console()

LOG_DIR = Path.home() / ".steelclaw" / "logs"


def show_logs(
    follow: bool = False,
    lines: int = 50,
    gateway: bool = False,
    app: bool = False,
) -> None:
    """Display daemon log output."""
    log_file = LOG_DIR / "steelclaw.log"

    if not log_file.exists():
        console.print("[yellow]No log file found. Is SteelClaw running in daemon mode?[/yellow]")
        console.print(f"Expected: {log_file}")
        return

    # Read last N lines
    all_lines = log_file.read_text().splitlines()

    if gateway or app:
        filter_str = "gateway" if gateway else "steelclaw.app"
        all_lines = [line for line in all_lines if filter_str in line.lower()]

    tail_lines = all_lines[-lines:]
    for line in tail_lines:
        console.print(line)

    if not follow:
        return

    # Follow mode
    console.print("[dim]--- Following log output (Ctrl+C to stop) ---[/dim]")
    try:
        with open(log_file, "r") as f:
            f.seek(0, 2)  # Seek to end
            while True:
                line = f.readline()
                if line:
                    line = line.rstrip()
                    if gateway and "gateway" not in line.lower():
                        continue
                    if app and "steelclaw.app" not in line.lower():
                        continue
                    console.print(line)
                else:
                    time.sleep(0.3)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped following logs[/dim]")
