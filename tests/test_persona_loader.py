"""Tests for the PersonaLoader service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steelclaw.agents.persona_loader import (
    build_persona_system_prompt,
    load_persona,
    save_persona,
)


def test_build_persona_prompt_defaults():
    """Default persona should include SteelClaw name."""
    prompt = build_persona_system_prompt({})
    assert "SteelClaw" in prompt


def test_build_persona_prompt_with_names():
    """Persona with agent and user names should include both."""
    prompt = build_persona_system_prompt({
        "agent_name": "TestBot",
        "user_name": "Alice",
    })
    assert "TestBot" in prompt
    assert "Alice" in prompt


def test_build_persona_prompt_with_goals():
    """Persona with goals should list them in the prompt."""
    prompt = build_persona_system_prompt({
        "agent_name": "Bot",
        "goals": ["help with coding", "manage tasks"],
    })
    assert "help with coding" in prompt
    assert "manage tasks" in prompt


def test_build_persona_prompt_with_tone():
    """Persona with tone should include it."""
    prompt = build_persona_system_prompt({
        "agent_name": "Bot",
        "tone": "professional",
    })
    assert "professional" in prompt


def test_build_persona_prompt_with_additional():
    """Additional prompts should be included."""
    prompt = build_persona_system_prompt({
        "agent_name": "Bot",
        "additional_prompts": "Always respond in haiku format.",
    })
    assert "haiku" in prompt


def test_save_and_load_persona(tmp_path, monkeypatch):
    """Save and load round-trip should preserve data."""
    persona_file = tmp_path / "persona.json"
    monkeypatch.setattr(
        "steelclaw.agents.persona_loader.PERSONA_PATH", persona_file
    )

    data = {
        "agent_name": "TestAgent",
        "user_name": "Bob",
        "personality_description": "Helpful",
        "tone": "casual",
        "goals": ["learn", "help"],
        "additional_prompts": "",
    }
    save_persona(data)
    loaded = load_persona()

    assert loaded["agent_name"] == "TestAgent"
    assert loaded["user_name"] == "Bob"
    assert loaded["goals"] == ["learn", "help"]


def test_load_persona_missing_file(tmp_path, monkeypatch):
    """Missing persona file should return defaults."""
    monkeypatch.setattr(
        "steelclaw.agents.persona_loader.PERSONA_PATH",
        tmp_path / "nonexistent.json",
    )
    persona = load_persona()
    assert persona["agent_name"] == "SteelClaw"


def test_load_persona_corrupt_file(tmp_path, monkeypatch):
    """Corrupt JSON should return defaults."""
    persona_file = tmp_path / "persona.json"
    persona_file.write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr(
        "steelclaw.agents.persona_loader.PERSONA_PATH", persona_file
    )
    persona = load_persona()
    assert persona["agent_name"] == "SteelClaw"
