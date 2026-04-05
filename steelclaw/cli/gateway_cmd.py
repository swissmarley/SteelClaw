"""CLI gateway connector management."""

from __future__ import annotations

import argparse
import sys

import httpx
from rich.console import Console

console = Console()
BASE_URL = "http://localhost:8000"


def handle_gateway(args: argparse.Namespace) -> None:
    action = getattr(args, "gateway_action", None)
    connector = getattr(args, "connector", None)

    if not action:
        _gateway_status()
        return

    if action == "start":
        _connector_action(connector, "start")
    elif action == "stop":
        _connector_action(connector, "stop")
    elif action == "restart":
        _connector_action(connector, "stop")
        _connector_action(connector, "start")
    elif action == "reset":
        _connector_action(connector, "stop")
        _connector_action(connector, "start")
    elif action == "kill":
        _connector_action(connector, "stop")
    else:
        _gateway_status()


def _gateway_status() -> None:
    try:
        resp = httpx.get(f"{BASE_URL}/info", timeout=10)
        resp.raise_for_status()
        info = resp.json()
        console.print("[bold]Gateway Status[/bold]")
        connectors = info.get("connectors", {})
        for name, status in connectors.items():
            style = "green" if status == "running" else "red"
            console.print(f"  {name}: [{style}]{status}[/{style}]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _connector_action(connector: str | None, action: str) -> None:
    if not connector:
        console.print(f"[red]Please specify a connector name for '{action}'[/red]")
        return

    console.print(f"[dim]{action.title()}ing connector: {connector}...[/dim]")
    # This would ideally call a REST API endpoint to control connectors
    # For now, connector lifecycle is managed through config changes
    try:
        if action == "stop":
            resp = httpx.put(
                f"{BASE_URL}/api/config/connectors/{connector}",
                json={"enabled": False},
                timeout=10,
            )
        else:
            resp = httpx.put(
                f"{BASE_URL}/api/config/connectors/{connector}",
                json={"enabled": True},
                timeout=10,
            )
        resp.raise_for_status()
        console.print(f"[green]Connector '{connector}' {action} complete[/green]")
        console.print("[dim]Restart SteelClaw for changes to take effect[/dim]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw[/red]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")
