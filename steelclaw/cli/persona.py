"""CLI persona configuration — interactive agent personality setup."""

from __future__ import annotations

import argparse
import json
import sys

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()
BASE_URL = "http://localhost:8000"


def handle_persona(args: argparse.Namespace) -> None:
    """Interactive persona configuration wizard."""
    try:
        import questionary
    except ImportError:
        console.print("[red]questionary is required. Install with: pip install questionary[/red]")
        return

    # Get the main agent
    try:
        resp = httpx.get(f"{BASE_URL}/api/agents", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print("[red]Cannot connect to SteelClaw. Is the server running?[/red]")
        sys.exit(1)

    agents = resp.json()
    main_agent = next((a for a in agents if a["is_main"]), None)
    if not main_agent:
        console.print("[red]No main agent found[/red]")
        return

    current_persona = main_agent.get("persona") or {}
    console.print(Panel("[bold]Agent Persona Configuration[/bold]", style="blue"))

    if current_persona:
        console.print(f"Current agent name: {current_persona.get('agent_name', 'SteelClaw')}")
        console.print(f"Current tone: {current_persona.get('tone', 'not set')}")
        console.print()

    agent_name = questionary.text(
        "What should the agent be called?",
        default=current_persona.get("agent_name", "SteelClaw"),
    ).ask()
    if agent_name is None:
        return

    user_name = questionary.text(
        "What should the agent call you?",
        default=current_persona.get("user_name", ""),
    ).ask()
    if user_name is None:
        return

    tone = questionary.select(
        "Communication tone:",
        choices=[
            "Professional — formal and structured",
            "Friendly — warm and conversational",
            "Casual — relaxed and informal",
            "Concise — minimal, to-the-point",
            "Technical — detailed and precise",
        ],
        default=None,
    ).ask()
    if tone is None:
        return
    tone = tone.split(" — ")[0].lower()

    style = questionary.select(
        "Response style:",
        choices=[
            "Verbose — detailed explanations",
            "Balanced — moderate detail",
            "Concise — brief and direct",
        ],
        default=None,
    ).ask()
    if style is None:
        return
    style = style.split(" — ")[0].lower()

    proactivity = questionary.select(
        "How proactive should the agent be?",
        choices=[
            "Proactive — suggest next steps, anticipate needs",
            "Reactive — only respond when asked",
            "Balanced — suggest when relevant",
        ],
        default=None,
    ).ask()
    if proactivity is None:
        return

    goals_text = questionary.text(
        "Primary goals/tasks (comma-separated, or empty):",
        default=", ".join(current_persona.get("goals", [])),
    ).ask()
    if goals_text is None:
        return
    goals = [g.strip() for g in goals_text.split(",") if g.strip()]

    # Build persona
    persona = {
        "agent_name": agent_name,
        "user_name": user_name,
        "tone": tone,
        "style": style,
        "proactivity": proactivity.split(" — ")[0].lower(),
        "goals": goals,
    }

    # Summary
    console.print()
    console.print(Panel(
        f"Agent: {agent_name}\n"
        f"User: {user_name}\n"
        f"Tone: {tone}\n"
        f"Style: {style}\n"
        f"Goals: {', '.join(goals) or 'none'}",
        title="Persona Summary",
        style="green",
    ))

    confirm = questionary.confirm("Apply this persona?", default=True).ask()
    if not confirm:
        console.print("[dim]Cancelled[/dim]")
        return

    # Save via API
    resp = httpx.put(
        f"{BASE_URL}/api/agents/{main_agent['id']}/persona",
        json=persona,
        timeout=10,
    )
    resp.raise_for_status()

    # Update display name
    httpx.put(
        f"{BASE_URL}/api/agents/{main_agent['id']}",
        json={"display_name": agent_name},
        timeout=10,
    )

    console.print(f"[green]Persona applied! {agent_name} is ready.[/green]")
