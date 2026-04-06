"""CLI session management — list/reset/delete sessions via REST API."""

from __future__ import annotations

import argparse
import sys

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"


def handle_sessions(args: argparse.Namespace) -> None:
    action = getattr(args, "sessions_action", None)
    platform = getattr(args, "platform", None)
    if action == "list":
        _list_sessions(platform=platform)
    elif action == "reset":
        _reset_session(args.session_id)
    elif action == "delete":
        _delete_session(args.session_id)
    else:
        _list_sessions(platform=platform)


def _list_sessions(platform: str | None = None) -> None:
    try:
        params = {}
        if platform:
            params["platform"] = platform
        resp = httpx.get(f"{BASE_URL}/api/sessions", params=params, timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    sessions = resp.json()
    if not sessions:
        if platform:
            console.print(f"[dim]No active sessions for platform: {platform}[/dim]")
        else:
            console.print("[dim]No active sessions[/dim]")
        return

    title = f"Sessions — {platform}" if platform else "Sessions"
    table = Table(title=title)
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Platform")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Connector")
    table.add_column("Last Activity")

    for s in sessions:
        status_style = {"active": "green", "idle": "yellow", "closed": "red"}.get(s["status"], "white")
        table.add_row(
            s["id"][:12],
            s["platform"],
            s["session_type"],
            f"[{status_style}]{s['status']}[/{status_style}]",
            s.get("connector_type") or "-",
            s.get("last_activity_at", "-")[:19] if s.get("last_activity_at") else "-",
        )

    console.print(table)


def _reset_session(session_id: str) -> None:
    try:
        resp = httpx.post(f"{BASE_URL}/api/sessions/{session_id}/reset", timeout=10)
        if resp.status_code == 404:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return
        resp.raise_for_status()
        console.print(f"[green]Session {session_id[:12]} reset successfully[/green]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _delete_session(session_id: str) -> None:
    try:
        resp = httpx.delete(f"{BASE_URL}/api/sessions/{session_id}", timeout=10)
        if resp.status_code == 404:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return
        resp.raise_for_status()
        console.print(f"[green]Session {session_id[:12]} deleted[/green]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)
