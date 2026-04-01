"""CLI app component management."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

console = Console()


def handle_app(args: argparse.Namespace) -> None:
    action = getattr(args, "app_action", None)

    if action == "start":
        from steelclaw.cli.daemon import start_daemon
        start_daemon()
    elif action == "stop":
        from steelclaw.cli.daemon import stop_daemon
        stop_daemon()
    elif action == "restart":
        from steelclaw.cli.daemon import restart_daemon
        restart_daemon()
    elif action == "reset":
        from steelclaw.cli.daemon import restart_daemon
        console.print("[dim]Resetting app (restart with fresh state)...[/dim]")
        restart_daemon()
    elif action == "kill":
        from steelclaw.cli.daemon import stop_daemon
        stop_daemon()
    else:
        from steelclaw.cli.daemon import show_status
        show_status()
