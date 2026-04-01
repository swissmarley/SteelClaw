"""Secure credential store for skill-specific API keys and secrets."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("steelclaw.skills.credentials")


def get_credential(skill_name: str, key: str) -> str | None:
    """Read a credential from config.json skill_configs section."""
    from steelclaw.paths import PROJECT_ROOT
    config_path = PROJECT_ROOT / "config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text())
        return config.get("agents", {}).get("skills", {}).get("skill_configs", {}).get(skill_name, {}).get(key)
    except (json.JSONDecodeError, KeyError):
        return None


def set_credential(skill_name: str, key: str, value: str) -> None:
    """Store a credential in config.json skill_configs section."""
    from steelclaw.paths import PROJECT_ROOT
    config_path = PROJECT_ROOT / "config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            pass

    agents = config.setdefault("agents", {})
    skills = agents.setdefault("skills", {})
    skill_configs = skills.setdefault("skill_configs", {})
    skill_config = skill_configs.setdefault(skill_name, {})
    skill_config[key] = value

    config_path.write_text(json.dumps(config, indent=2))
    logger.info("Credential saved for skill '%s' key '%s'", skill_name, key)


def get_all_credentials(skill_name: str) -> dict[str, str]:
    """Read all credentials for a given skill."""
    from steelclaw.paths import PROJECT_ROOT
    config_path = PROJECT_ROOT / "config.json"
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text())
        return config.get("agents", {}).get("skills", {}).get("skill_configs", {}).get(skill_name, {})
    except (json.JSONDecodeError, KeyError):
        return {}
