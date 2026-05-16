"""CLI skills management — list/create/import/export/delete/enable/disable/generate/test skills."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import questionary
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"
GLOBAL_SKILLS_DIR = Path.home() / ".steelclaw" / "claude-skills"


def handle_skills(args: argparse.Namespace) -> None:
    action = getattr(args, "skills_action", None)
    if action == "list":
        _list_skills()
    elif action == "view":
        _view_skill(args.name)
    elif action == "create":
        _create_skill()
    elif action == "import":
        _import_skill(args.path)
    elif action == "export":
        _export_skill(args.name, getattr(args, "output", None))
    elif action == "delete":
        _delete_skill(args.name)
    elif action == "generate":
        _generate_skill(args.description)
    elif action == "enable":
        _enable_skill(args.name)
    elif action == "disable":
        _disable_skill(args.name)
    elif action == "test":
        _test_skill(args.message)
    else:
        _list_skills()


def _api(path: str, method: str = "GET", json_data=None, files=None) -> dict:
    """Make an API call to the skills endpoint."""
    url = f"{BASE_URL}/api/skills{path}"
    try:
        if method == "GET":
            resp = httpx.get(url, timeout=10)
        elif method == "POST":
            resp = httpx.post(url, json=json_data, timeout=30, files=files)
        elif method == "DELETE":
            resp = httpx.delete(url, timeout=10)
        else:
            resp = httpx.request(method, url, json=json_data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)


def _list_skills() -> None:
    skills = _api("")
    if not skills:
        console.print("[dim]No skills installed. Create or import one to get started.[/dim]")
        return

    table = Table(title="Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Author")
    table.add_column("Scope")
    table.add_column("Triggers")
    table.add_column("Status")

    for s in skills:
        triggers = ", ".join(s.get("triggers", []))
        status = "[green]enabled[/green]" if s.get("enabled", True) else "[dim]disabled[/dim]"
        table.add_row(
            s["name"],
            s.get("version", "-"),
            s.get("author", "-"),
            s.get("scope", "-"),
            triggers or "[dim]none[/dim]",
            status,
        )

    console.print(table)


def _view_skill(name: str) -> None:
    skill = _api(f"/{name}")
    console.print(f"\n[bold cyan]{skill['name']}[/bold cyan] v{skill.get('version', '?')}")
    console.print(f"  {skill.get('description', 'No description')}")
    console.print(f"  Author: {skill.get('author', 'Unknown')}")
    console.print(f"  Scope: {skill.get('scope', '?')}")
    console.print(f"  Enabled: {'Yes' if skill.get('enabled') else 'No'}")
    triggers = skill.get("triggers", [])
    if triggers:
        console.print(f"  Triggers: {', '.join(triggers)}")
    if skill.get("system_prompt"):
        console.print("\n[bold]System Prompt:[/bold]")
        console.print(skill["system_prompt"])
    if skill.get("raw_content"):
        console.print("\n[bold]SKILL.md:[/bold]")
        console.print(skill["raw_content"])


def _create_skill() -> None:
    """Interactive skill creation wizard."""
    console.print("[bold]Create New Skill[/bold]\n")
    name = questionary.text("Skill name (snake_case):").ask()
    if not name:
        console.print("[dim]Cancelled.[/dim]")
        return

    description = questionary.text("Short description:").ask() or ""
    version = questionary.text("Version:", default="1.0.0").ask() or "1.0.0"
    author = questionary.text("Author:").ask() or ""
    triggers_str = questionary.text("Trigger keywords (comma-separated):").ask() or ""
    triggers = [t.strip() for t in triggers_str.split(",") if t.strip()]
    system_prompt = questionary.text("Skill instructions / system prompt:").ask() or ""

    result = _api("", method="POST", json_data={
        "name": name,
        "description": description,
        "version": version,
        "author": author,
        "triggers": triggers,
        "system_prompt": system_prompt,
        "scope": "global",
    })
    console.print(f"[green]Skill '{result.get('skill', name)}' created successfully.[/green]")


def _import_skill(path: str) -> None:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Path not found: {source}[/red]")
        return

    if source.is_file() and source.suffix in (".md", ".zip"):
        # Upload via API
        with open(source, "rb") as f:
            files = {"file": (source.name, f)}
            result = _api("/import", method="POST", files=files)
        console.print(f"[green]Skill '{result.get('skill', '?')}' imported.[/green]")
    elif source.is_dir():
        result = _api("/import-path", method="POST", json_data={"path": str(source)})
        console.print(f"[green]Skill '{result.get('skill', '?')}' imported from directory.[/green]")
    else:
        console.print(f"[red]Unsupported file type. Use .md, .zip, or directory.[/red]")


def _export_skill(name: str, output: str | None) -> None:
    result = _api(f"/{name}/export")
    zip_path = result.get("path", "")
    if output:
        dest = Path(output).expanduser().resolve()
        shutil.copy2(zip_path, dest)
        console.print(f"[green]Skill '{name}' exported to {dest}[/green]")
    else:
        console.print(f"[green]Skill '{name}' exported to {zip_path}[/green]")


def _delete_skill(name: str) -> None:
    confirm = questionary.confirm(f"Delete skill '{name}'? This cannot be undone.").ask()
    if not confirm:
        console.print("[dim]Cancelled.[/dim]")
        return

    result = _api(f"/{name}", method="DELETE")
    console.print(f"[green]Skill '{result.get('skill', name)}' deleted.[/green]")


def _generate_skill(description: str) -> None:
    console.print(f"[bold]Generating skill from description...[/bold]\n")
    result = _api("/generate", method="POST", json_data={"description": description})
    console.print(f"[green]Skill '{result.get('skill', '?')}' generated.[/green]")


def _enable_skill(name: str) -> None:
    result = _api(f"/{name}/enable", method="POST")
    console.print(f"[green]Skill '{result.get('skill', name)}' enabled.[/green]")


def _disable_skill(name: str) -> None:
    result = _api(f"/{name}/disable", method="POST")
    console.print(f"[yellow]Skill '{result.get('skill', name)}' disabled.[/yellow]")


def _test_skill(message: str) -> None:
    result = _api("/test", method="POST", json_data={"message": message})
    matched = result.get("matched_skills", [])
    if matched:
        console.print(f"[bold]Skills matched for: \"{message}\"[/bold]\n")
        for s in matched:
            triggers = ", ".join(s.get("matched_triggers", []))
            console.print(f"  [cyan]{s['name']}[/cyan] v{s.get('version', '?')} — {s.get('description', '')}")
            console.print(f"    Matched triggers: {triggers}")
    else:
        console.print(f"[dim]No skills matched for: \"{message}\"[/dim]")


def register_skills_parser(subparsers) -> None:
    """Register the skills subcommand parser."""
    parser = subparsers.add_parser("skills", help="Manage Claude-compatible skills")
    skills_actions = parser.add_subparsers(dest="skills_action")

    # list
    skills_actions.add_parser("list", help="List all installed skills")

    # view
    view_parser = skills_actions.add_parser("view", help="Show skill details")
    view_parser.add_argument("name", help="Skill name")

    # create
    skills_actions.add_parser("create", help="Create a new skill (interactive wizard)")

    # import
    import_parser = skills_actions.add_parser("import", help="Import a skill from file or directory")
    import_parser.add_argument("path", help="Path to SKILL.md, .zip, or skill directory")

    # export
    export_parser = skills_actions.add_parser("export", help="Export a skill as zip")
    export_parser.add_argument("name", help="Skill name")
    export_parser.add_argument("--output", "-o", help="Output path", default=None)

    # delete
    delete_parser = skills_actions.add_parser("delete", help="Delete a skill")
    delete_parser.add_argument("name", help="Skill name")

    # generate
    gen_parser = skills_actions.add_parser("generate", help="AI-generate a skill from description")
    gen_parser.add_argument("description", help="What the skill should do")

    # enable
    enable_parser = skills_actions.add_parser("enable", help="Enable a skill")
    enable_parser.add_argument("name", help="Skill name")

    # disable
    disable_parser = skills_actions.add_parser("disable", help="Disable a skill")
    disable_parser.add_argument("name", help="Skill name")

    # test
    test_parser = skills_actions.add_parser("test", help="Test trigger matching")
    test_parser.add_argument("message", help="Message to test against triggers")

    parser.set_defaults(func=handle_skills)