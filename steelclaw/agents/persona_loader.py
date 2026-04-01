"""PersonaLoader — reads persona config and builds system prompt prefix for every turn."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("steelclaw.agents.persona_loader")

PERSONA_PATH = Path.home() / ".steelclaw" / "persona.json"

_DEFAULT_PERSONA: dict[str, Any] = {
    "agent_name": "SteelClaw",
    "user_name": "",
    "personality_description": "A helpful, autonomous AI assistant",
    "tone": "friendly",
    "goals": [],
    "additional_prompts": "",
}


def load_persona() -> dict[str, Any]:
    """Read persona from ~/.steelclaw/persona.json. Returns defaults if missing."""
    if not PERSONA_PATH.exists():
        return dict(_DEFAULT_PERSONA)
    try:
        data = json.loads(PERSONA_PATH.read_text(encoding="utf-8"))
        merged = dict(_DEFAULT_PERSONA)
        merged.update({k: v for k, v in data.items() if v})
        return merged
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read persona.json, using defaults")
        return dict(_DEFAULT_PERSONA)


def save_persona(data: dict[str, Any]) -> None:
    """Write persona to ~/.steelclaw/persona.json."""
    PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERSONA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_persona_system_prompt(persona: dict[str, Any] | None = None) -> str:
    """Build a system prompt prefix from persona data.

    Called every turn to ensure persona survives context resets.
    """
    if persona is None:
        persona = load_persona()

    parts: list[str] = []

    agent_name = persona.get("agent_name") or "SteelClaw"
    parts.append(f"You are {agent_name}, a personal AI assistant.")

    user_name = persona.get("user_name")
    if user_name:
        parts.append(f"Your user's name is {user_name}. Address them by name when appropriate.")

    personality = persona.get("personality_description")
    if personality:
        parts.append(f"Your personality: {personality}")

    tone = persona.get("tone")
    if tone:
        parts.append(f"Your tone: {tone}")

    goals = persona.get("goals", [])
    if goals:
        goals_str = "\n".join(f"  - {g}" for g in goals)
        parts.append(f"Your primary goals:\n{goals_str}")

    additional = persona.get("additional_prompts")
    if additional:
        parts.append(f"Additional instructions: {additional}")

    if user_name:
        parts.append(f"Always address the user by their name: {user_name}.")

    return "\n".join(parts)
