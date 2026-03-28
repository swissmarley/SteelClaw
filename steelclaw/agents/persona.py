"""Agent persona engine — builds system prompt prefixes from persona config."""

from __future__ import annotations

import json
import logging
from typing import Any

from steelclaw.db.models import AgentProfile

logger = logging.getLogger("steelclaw.agents.persona")


def build_persona_prompt(profile: AgentProfile) -> str:
    """Convert a structured persona JSON into a natural language system prompt prefix."""
    if not profile.persona_json:
        return ""

    try:
        persona = json.loads(profile.persona_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    parts = []

    agent_name = persona.get("agent_name")
    if agent_name:
        parts.append(f"Your name is {agent_name}.")

    user_name = persona.get("user_name")
    if user_name:
        parts.append(f"The user's name is {user_name}. Address them by name when appropriate.")

    tone = persona.get("tone")
    if tone:
        tone_map = {
            "professional": "Communicate in a professional, formal tone.",
            "friendly": "Communicate in a warm, friendly tone.",
            "casual": "Communicate in a casual, relaxed tone.",
            "concise": "Be extremely concise and to-the-point.",
            "technical": "Use precise technical language and provide detailed explanations.",
        }
        parts.append(tone_map.get(tone, f"Communicate in a {tone} tone."))

    style = persona.get("style")
    if style:
        style_map = {
            "verbose": "Provide thorough, detailed explanations.",
            "balanced": "Provide balanced responses with moderate detail.",
            "concise": "Keep responses brief and direct.",
        }
        parts.append(style_map.get(style, f"Your response style is {style}."))

    proactivity = persona.get("proactivity")
    if proactivity:
        if proactivity == "proactive":
            parts.append("Be proactive — suggest next steps and anticipate user needs.")
        elif proactivity == "reactive":
            parts.append("Only respond to what is directly asked. Do not volunteer suggestions.")

    goals = persona.get("goals", [])
    if goals:
        parts.append(f"The user's primary goals are: {', '.join(goals)}. Keep these in mind.")

    extension = persona.get("system_prompt_extension")
    if extension:
        parts.append(extension)

    return " ".join(parts)


def format_user_facts(facts: list[dict[str, str]]) -> str:
    """Format user facts as context for the system prompt."""
    if not facts:
        return ""

    lines = ["[Known facts about the user:]"]
    for fact in facts:
        lines.append(f"  - {fact['fact_key']}: {fact['fact_value']}")
    lines.append("[End of user facts]")
    return "\n".join(lines)
