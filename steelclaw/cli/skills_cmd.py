"""CLI skill management — list/install/enable/disable/configure skills."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import httpx
import questionary
from rich.console import Console
from rich.table import Table

console = Console()
BASE_URL = "http://localhost:8000"
GLOBAL_SKILLS_DIR = Path.home() / ".steelclaw" / "skills"


def handle_skills(args: argparse.Namespace) -> None:
    action = getattr(args, "skills_action", None)
    if action == "list":
        _list_skills()
    elif action == "install":
        _install_skill(args.path)
    elif action == "enable":
        _enable_skill(args.name)
    elif action == "disable":
        _disable_skill(args.name)
    elif action == "configure":
        _configure_skill(args.name)
    else:
        _list_skills()


def _list_skills() -> None:
    try:
        resp = httpx.get(f"{BASE_URL}/api/skills", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    skills = resp.json()
    if not skills:
        console.print("[dim]No skills loaded[/dim]")
        return

    table = Table(title="Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Scope")
    table.add_column("Tools")
    table.add_column("Status")

    for s in skills:
        tool_count = str(len(s.get("tools", [])))
        status = "[green]enabled[/green]"
        table.add_row(s["name"], s.get("version", "-"), s.get("scope", "-"), tool_count, status)

    console.print(table)


def _install_skill(source_path: str) -> None:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        console.print(f"[red]Source path not found: {source}[/red]")
        return

    skill_md = source / "SKILL.md"
    if not skill_md.exists():
        console.print(f"[red]No SKILL.md found in {source}. Is this a valid skill?[/red]")
        return

    dest = GLOBAL_SKILLS_DIR / source.name
    GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        console.print(f"[yellow]Skill '{source.name}' already installed. Overwriting...[/yellow]")
        shutil.rmtree(dest)

    shutil.copytree(source, dest)
    console.print(f"[green]Skill '{source.name}' installed to {dest}[/green]")
    console.print("Restart SteelClaw or reload skills to activate.")


def _enable_skill(name: str) -> None:
    _update_config_disabled(name, enable=True)
    console.print(f"[green]Skill '{name}' enabled[/green]")


def _disable_skill(name: str) -> None:
    _update_config_disabled(name, enable=False)
    console.print(f"[yellow]Skill '{name}' disabled[/yellow]")


def _update_config_disabled(name: str, enable: bool) -> None:
    from steelclaw.paths import PROJECT_ROOT
    config_path = PROJECT_ROOT / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    agents = config.setdefault("agents", {})
    skills = agents.setdefault("skills", {})
    disabled = skills.setdefault("disabled_skills", [])

    if enable:
        if name in disabled:
            disabled.remove(name)
    else:
        if name not in disabled:
            disabled.append(name)

    config_path.write_text(json.dumps(config, indent=2))


def _configure_skill(name: str | None) -> None:
    if name is not None:
        _configure_skill_named(name)
        return
    _configure_skill_interactive()


def _configure_skill_interactive() -> None:
    """Show a questionary skill-selection menu, then prompt for credentials."""
    try:
        resp = httpx.get(f"{BASE_URL}/api/skills", timeout=10)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        console.print(f"[red]Cannot connect to SteelClaw: {e}[/red]")
        sys.exit(1)

    skills = resp.json()
    skills_with_creds = [s for s in skills if s.get("required_credentials")]
    if not skills_with_creds:
        console.print("[dim]No skills require credentials[/dim]")
        return

    choices = []
    for s in skills_with_creds:
        try:
            cred_resp = httpx.get(f"{BASE_URL}/api/skills/{s['name']}/credentials", timeout=10)
            creds = cred_resp.json().get("credentials", [])
            all_set = all(c.get("is_set") for c in creds) if creds else False
        except Exception:
            all_set = False
        status = "✓ configured" if all_set else "✗ not configured"
        choices.append(questionary.Choice(title=f"{s['name']}  [{status}]", value=s["name"]))

    selected = questionary.select(
        "Select a skill to configure:",
        choices=choices,
    ).ask()
    if not selected:
        return

    _configure_skill_named(selected)


def _configure_skill_named(name: str) -> None:
    """Configure a specific skill by prompting for each credential field."""
    cred_fields: list[dict] = []
    try:
        cred_resp = httpx.get(f"{BASE_URL}/api/skills/{name}/credentials", timeout=10)
        if cred_resp.status_code == 200:
            cred_fields = cred_resp.json().get("credentials", [])
    except httpx.ConnectError:
        pass  # Fall through to manual key=value entry

    if cred_fields:
        console.print(f"[bold]Configure skill: {name}[/bold]")
        collected: dict[str, str] = {}
        for field in cred_fields:
            key = field["key"]
            label = field.get("label", key)
            is_secret = field.get("type") == "password"
            current_masked = field.get("value", "")
            if current_masked:
                label = f"{label} (currently set — leave blank to keep)"
            value = (
                questionary.password(f"{label}:").ask()
                if is_secret
                else questionary.text(f"{label}:").ask()
            )
            if value is None:
                console.print("[dim]Cancelled.[/dim]")
                return
            if value:
                collected[key] = value
        if not collected:
            console.print("[dim]No changes made[/dim]")
            return
        try:
            put_resp = httpx.put(
                f"{BASE_URL}/api/skills/{name}/credentials",
                json={"credentials": collected},
                timeout=10,
            )
            put_resp.raise_for_status()
            console.print(f"[green]✓ Credentials saved for {name}.[/green]")
        except httpx.HTTPError as e:
            console.print(f"[red]Cannot connect to SteelClaw: {e}[/red]")
            sys.exit(1)
    else:
        # Fallback: manual key=value entry (server not running or skill not found)
        from steelclaw.paths import PROJECT_ROOT
        config_path = PROJECT_ROOT / "config.json"
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text())

        agents = config.setdefault("agents", {})
        skills = agents.setdefault("skills", {})
        skill_configs = skills.setdefault("skill_configs", {})
        current = skill_configs.get(name, {})

        console.print(f"[bold]Configure skill: {name}[/bold]")
        if current:
            console.print(f"Current config: {json.dumps(current, indent=2)}")

        console.print("Enter key=value pairs (empty line to finish):")
        while True:
            line = console.input("> ").strip()
            if not line:
                break
            if "=" not in line:
                console.print("[red]Format: key=value[/red]")
                continue
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()

        skill_configs[name] = current
        config_path.write_text(json.dumps(config, indent=2))
        console.print(f"[green]Skill '{name}' configuration saved[/green]")
