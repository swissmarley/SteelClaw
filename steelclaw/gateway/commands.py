"""Centralized slash command registry for all messenger platform connectors.

Each entry exposes:
  name        – command name without the leading slash
  description – short human-readable description shown in autocomplete menus
  params      – optional list of parameter hints (informational only)
"""

from __future__ import annotations

from typing import TypedDict


class SlashCommand(TypedDict, total=False):
    name: str
    description: str
    params: list[str]


# Commands mirroring the SteelClaw CLI and core capabilities.
SLASH_COMMANDS: list[SlashCommand] = [
    {
        "name": "help",
        "description": "Show available commands and usage information",
    },
    {
        "name": "status",
        "description": "Show current bot and session status",
    },
    {
        "name": "run",
        "description": "Run a task or shell command",
        "params": ["task"],
    },
    {
        "name": "stop",
        "description": "Stop the current running task",
    },
    {
        "name": "config",
        "description": "View or update bot configuration",
        "params": ["key", "value"],
    },
    {
        "name": "memory",
        "description": "Manage persistent memory (list, clear, search)",
        "params": ["action"],
    },
]
