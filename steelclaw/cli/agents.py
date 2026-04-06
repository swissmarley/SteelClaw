"""CLI agent management — list/add/delete agents via REST API."""

from __future__ import annotations

import argparse
import json
import sys

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"


def handle_agents(args: argparse.Namespace) -> None:
    action = getattr(args, "agents_action", None)
    if action == "list":
        _list_agents()
    elif action == "add":
        _add_agent(
            args.name,
            model=args.model,
            persona_file=args.persona,
            parent=getattr(args, "parent", None),
            system_prompt=getattr(args, "system_prompt", None),
        )
    elif action == "delete":
        _delete_agent(args.name)
    elif action == "status":
        _list_agents()
    else:
        _list_agents()


def _list_agents() -> None:
    try:
        resp = httpx.get(f"{BASE_URL}/api/agents", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    agents = resp.json()
    if not agents:
        console.print("[dim]No agents configured[/dim]")
        return

    # Build a name → display_name lookup for parent resolution
    id_to_name: dict[str, str] = {a["id"]: a["name"] for a in agents}

    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Model")
    table.add_column("Main")
    table.add_column("Parent")
    table.add_column("Active")
    table.add_column("Created")

    for a in agents:
        parent_name = id_to_name.get(a.get("parent_agent_id") or "") or "—"
        table.add_row(
            a["name"],
            a["display_name"],
            a.get("model_override") or "(default)",
            "[green]Yes[/green]" if a["is_main"] else "No",
            f"[dim]{parent_name}[/dim]" if parent_name != "—" else "[dim]—[/dim]",
            "[green]Yes[/green]" if a["is_active"] else "[red]No[/red]",
            a["created_at"][:10],
        )

    console.print(table)


def _add_agent(
    name: str,
    model: str | None = None,
    persona_file: str | None = None,
    parent: str | None = None,
    system_prompt: str | None = None,
) -> None:
    body: dict = {"name": name}
    if model:
        body["model_override"] = model
    if system_prompt:
        body["system_prompt"] = system_prompt

    if persona_file:
        try:
            with open(persona_file) as f:
                body["persona_json"] = f.read()
        except FileNotFoundError:
            console.print(f"[red]Persona file not found: {persona_file}[/red]")
            return

    # Resolve parent agent name → ID
    if parent:
        try:
            resp = httpx.get(f"{BASE_URL}/api/agents", timeout=10)
            resp.raise_for_status()
            agents = resp.json()
        except httpx.ConnectError:
            console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
            sys.exit(1)

        parent_agent = next((a for a in agents if a["name"] == parent), None)
        if not parent_agent:
            console.print(f"[red]Parent agent '{parent}' not found[/red]")
            return
        body["parent_agent_id"] = parent_agent["id"]

    try:
        resp = httpx.post(f"{BASE_URL}/api/agents", json=body, timeout=10)
        if resp.status_code == 400:
            d = resp.json()
            console.print(f"[red]{d.get('detail', 'Bad request')}[/red]")
            return
        if resp.status_code == 409:
            console.print(f"[red]Agent '{name}' already exists[/red]")
            return
        resp.raise_for_status()
        agent = resp.json()
        parent_info = f" (sub-agent of {parent})" if parent else ""
        console.print(f"[green]Agent '{name}' created{parent_info}[/green]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _delete_agent(name: str) -> None:
    # First find the agent by name to get its ID
    try:
        resp = httpx.get(f"{BASE_URL}/api/agents", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    agents = resp.json()
    agent = next((a for a in agents if a["name"] == name), None)
    if not agent:
        console.print(f"[red]Agent '{name}' not found[/red]")
        return

    if agent["is_main"]:
        console.print("[red]Cannot delete the main agent[/red]")
        return

    resp = httpx.delete(f"{BASE_URL}/api/agents/{agent['id']}", timeout=10)
    resp.raise_for_status()
    console.print(f"[green]Agent '{name}' deleted[/green]")
