"""CLI configuration management — show/get/set config values via dot-notation."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich import box

console = Console()


def handle_config(args: argparse.Namespace) -> None:
    action = getattr(args, "config_action", None)
    if action == "get":
        _config_get(args.key)
    elif action == "set":
        _config_set(args.key, args.value)
    else:
        _config_show()


def _get_config_path() -> Path:
    from steelclaw.paths import PROJECT_ROOT
    return PROJECT_ROOT / "config.json"


def _load_config() -> dict:
    path = _get_config_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_config(config: dict) -> None:
    """Write config atomically: write to a temp file then os.replace().

    This prevents partial writes from corrupting config.json if the process
    is interrupted mid-write (e.g. power loss, SIGKILL).
    """
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(config, indent=2)
    # NamedTemporaryFile in the same directory ensures os.replace is atomic
    # (same filesystem), and delete=False lets us manage the file manually.
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _config_show() -> None:
    """Display the full config.json with syntax highlighting."""
    path = _get_config_path()
    if not path.exists():
        console.print(f"[yellow]No config.json found at {path}[/yellow]")
        console.print("[dim]Run 'steelclaw setup' to create a configuration.[/dim]")
        return

    content = path.read_text(encoding="utf-8")
    syntax = Syntax(content, "json", theme="monokai", line_numbers=True)
    console.print(Panel(
        syntax,
        title=f"[bold cyan] Config: {path} [/]",
        border_style="blue",
        box=box.ROUNDED,
    ))


def _config_get(key: str) -> None:
    """Get a config value by dot-notation key (e.g. agents.llm.default_model)."""
    config = _load_config()
    parts = key.split(".")

    current = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            console.print(f"[red]Key not found: {key}[/red]")
            console.print("[dim]Use 'steelclaw config show' to see all available keys.[/dim]")
            return

    if isinstance(current, (dict, list)):
        syntax = Syntax(json.dumps(current, indent=2), "json", theme="monokai")
        console.print(Panel(syntax, title=f"[bold cyan] {key} [/]", border_style="blue", box=box.ROUNDED))
    else:
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim", min_width=10)
        tbl.add_column()
        tbl.add_row("Key", f"[bold cyan]{key}[/]")
        tbl.add_row("Value", f"[bold green]{current}[/]")
        tbl.add_row("Type", f"[dim]{type(current).__name__}[/]")
        console.print(Panel(tbl, title="[bold cyan] Config Value [/]", border_style="blue", box=box.ROUNDED))


def _config_set(key: str, value: str) -> None:
    """Set a config value by dot-notation key."""
    config = _load_config()
    parts = key.split(".")

    # Try to parse value as JSON (handles booleans, ints, null, etc.)
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value  # Keep as string

    # Navigate to the parent dict, creating missing levels
    current = config
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]

    current[parts[-1]] = parsed_value
    _save_config(config)

    display_val = json.dumps(parsed_value) if not isinstance(parsed_value, str) else parsed_value
    console.print(f"[green]✓[/] [bold cyan]{key}[/] = [bold]{display_val}[/]")
    console.print("[dim]  Restart the server for changes to take effect.[/dim]")
