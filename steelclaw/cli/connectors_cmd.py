"""CLI connector management — list, configure, enable, disable, status."""

from __future__ import annotations

import sys

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"

# Per-connector credential field definitions.
# Each entry: list of {key, label, type} where type is "password" or "text".
_CONNECTOR_FIELDS: dict[str, list[dict]] = {
    "slack": [
        {"key": "token", "label": "Bot Token (xoxb-...)", "type": "password"},
        {"key": "app_token", "label": "App-Level Token (xapp-...)", "type": "password"},
    ],
    "telegram": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "discord": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "whatsapp": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
    "signal": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
    "matrix": [
        {"key": "token", "label": "Access Token", "type": "password"},
        {"key": "homeserver", "label": "Homeserver URL (e.g. https://matrix.org)", "type": "text"},
    ],
    "mattermost": [
        {"key": "token", "label": "Bot Token", "type": "password"},
    ],
    "teams": [
        {"key": "token", "label": "Bot Token", "type": "password"},
        {"key": "signing_secret", "label": "Signing Secret", "type": "password"},
    ],
    "imessage": [
        {"key": "token", "label": "API Token", "type": "password"},
    ],
}


def handle_connectors(args) -> None:
    action = getattr(args, "connectors_action", None)
    if action == "list":
        _list_connectors()
    elif action == "configure":
        _configure_connector(getattr(args, "name", None))
    elif action == "enable":
        _enable_connector(args.name)
    elif action == "disable":
        _disable_connector(args.name)
    elif action == "status":
        _status_connector(args.name)
    else:
        _list_connectors()


def _get_connectors() -> dict:
    """Fetch connector status from the running server."""
    try:
        resp = httpx.get(f"{BASE_URL}/api/config/connectors", timeout=10)
        resp.raise_for_status()
        return resp.json().get("connectors", {})
    except httpx.HTTPError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _list_connectors() -> None:
    connectors = _get_connectors()
    if not connectors:
        console.print("[dim]No connectors configured[/dim]")
        return

    table = Table(title="Connectors")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Error", style="red")

    for name, info in connectors.items():
        status = info.get("status", "unknown")
        if status == "running":
            status_str = "[green]running[/green]"
        elif status == "enabled_not_running":
            status_str = "[yellow]enabled (not running)[/yellow]"
        else:
            status_str = "[dim]disabled[/dim]"
        error = info.get("last_error", "")
        table.add_row(name, status_str, error or "")

    console.print(table)


def _configure_connector(name: str | None) -> None:
    if name is None:
        _configure_connector_interactive()
    else:
        _configure_connector_named(name)


def _configure_connector_interactive() -> None:
    import questionary

    connectors = _get_connectors()
    all_names = list(_CONNECTOR_FIELDS.keys())

    choices = []
    for cname in all_names:
        info = connectors.get(cname, {})
        status = info.get("status", "disabled")
        status_label = "running" if status == "running" else ("enabled" if "enabled" in status else "disabled")
        choices.append(questionary.Choice(title=f"{cname}  [{status_label}]", value=cname))

    selected = questionary.select("Select a connector to configure:", choices=choices).ask()
    if not selected:
        return
    _configure_connector_named(selected)


def _configure_connector_named(name: str) -> None:
    import questionary

    fields = _CONNECTOR_FIELDS.get(name)
    if not fields:
        console.print(f"[red]Unknown connector '{name}'. Known: {', '.join(_CONNECTOR_FIELDS)}[/red]")
        return

    # Fetch current config to pre-populate non-secret fields
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})

    console.print(f"[bold]Configure connector: {name}[/bold]")
    collected: dict = {"enabled": current_cfg.get("enabled", False)}

    for field in fields:
        key = field["key"]
        label = field["label"]
        is_secret = field["type"] == "password"
        current_val = current_cfg.get(key, "")

        if is_secret and current_val:
            prompt_label = f"{label} (currently set — leave blank to keep)"
        else:
            prompt_label = label

        value = (
            questionary.password(f"{prompt_label}:").ask()
            if is_secret
            else questionary.text(f"{prompt_label}:", default=current_val or "").ask()
        )
        if value:
            collected[key] = value
        elif current_val:
            collected[key] = current_val  # re-send existing (masked) value

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=collected,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "error":
            console.print(f"[red]Error: {result.get('message')}[/red]")
        else:
            console.print(f"[green]✓ Connector '{name}' configured.[/green]")
    except httpx.HTTPError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _enable_connector(name: str) -> None:
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})
    payload = dict(current_cfg)
    payload["enabled"] = True

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "error":
            console.print(f"[red]Connector '{name}' failed to start: {result.get('message')}[/red]")
        elif result.get("status") == "running":
            console.print(f"[green]Connector '{name}' is now running.[/green]")
        else:
            console.print(f"[yellow]Connector '{name}' status: {result.get('status')}[/yellow]")
    except httpx.HTTPError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _disable_connector(name: str) -> None:
    connectors = _get_connectors()
    current_cfg = connectors.get(name, {}).get("config", {})
    payload = dict(current_cfg)
    payload["enabled"] = False

    try:
        resp = httpx.put(
            f"{BASE_URL}/api/config/connectors/{name}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        console.print(f"[yellow]Connector '{name}' disabled.[/yellow]")
    except httpx.HTTPError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _status_connector(name: str) -> None:
    connectors = _get_connectors()
    info = connectors.get(name)
    if info is None:
        console.print(f"[red]Connector '{name}' not found in config.[/red]")
        return

    status = info.get("status", "unknown")
    console.print(f"[bold]{name}[/bold]")
    console.print(f"  Status:  {status}")
    if info.get("last_error"):
        console.print(f"  Error:   [red]{info['last_error']}[/red]")
    cfg = info.get("config", {})
    if cfg:
        console.print("  Config:")
        for k, v in cfg.items():
            if k == "enabled":
                continue
            console.print(f"    {k}: {v}")
