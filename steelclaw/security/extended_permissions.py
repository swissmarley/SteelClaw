"""Extended capability-level permission system backed by ~/.steelclaw/permissions.yaml.

Provides granular, category-based toggles (filesystem, processes, network,
packages, environment, cron) that layer on top of the existing three-tier
command approval model.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("steelclaw.security.extended_permissions")

# Default permissions.yaml template written when the file is absent
_DEFAULT_YAML = """\
# SteelClaw — Extended Capability Permissions
# Toggle each capability category on or off. Changes take effect on restart.
# See docs for details on each category.

capabilities:
  filesystem:
    enabled: true
    # Restrict to specific paths (empty = all paths allowed)
    allowed_paths: []
    # Allowed operations (read, write, delete)
    operations: [read, write, delete]

  processes:
    enabled: true  # kill, pkill, systemctl, service

  network:
    enabled: false  # curl, wget, nc, nmap, ssh

  packages:
    enabled: false  # pip install, apt-get install, brew install, npm install
    managers: []    # e.g. [pip, apt]

  environment:
    enabled: true   # export, env, printenv, .env modifications

  cron:
    enabled: false  # crontab, at, cron

sudo:
  enabled: false                          # Master sudo toggle — NEVER auto-approve
  whitelist: []                           # Glob patterns of pre-approved sudo commands
  audit_log: "~/.steelclaw/sudo_audit.log"
  session_timeout: 30                     # Seconds before approval expires
"""

# Mapping from capability category to command-prefix patterns
_CATEGORY_PATTERNS: dict[str, list[re.Pattern]] = {
    "filesystem": [
        re.compile(r"^(rm|mv|cp|cat|echo\s+.+>\s*|tee|truncate|touch|mkdir|rmdir|chmod|chown)\b", re.I),
        re.compile(r"^(find|locate|ls|dir)\b", re.I),
        re.compile(r">\s*\S"),  # redirect to file
    ],
    "processes": [
        re.compile(r"^(kill|pkill|killall|systemctl|service|supervisorctl|launchctl)\b", re.I),
    ],
    "network": [
        re.compile(r"^(curl|wget|nc|ncat|netcat|nmap|ssh|scp|rsync|ftp|sftp|dig|host|nslookup)\b", re.I),
        re.compile(r"^(ping|traceroute|tracepath|mtr|ifconfig|ip\s+addr|netstat|ss)\b", re.I),
    ],
    "packages": [
        re.compile(r"^pip\d*\s+(install|uninstall|upgrade)\b", re.I),
        re.compile(r"^(apt-get|apt|dpkg)\s+(install|remove|purge|upgrade)\b", re.I),
        re.compile(r"^(brew)\s+(install|uninstall|upgrade|reinstall)\b", re.I),
        re.compile(r"^npm\s+(install|uninstall|update)\b", re.I),
        re.compile(r"^(yarn|pnpm)\s+(add|remove|upgrade)\b", re.I),
    ],
    "environment": [
        re.compile(r"^(export|unset)\s+\w", re.I),
        re.compile(r"^(env|printenv|set)\b", re.I),
        re.compile(r"\.env\b", re.I),
    ],
    "cron": [
        re.compile(r"^(crontab|at|batch|anacron)\b", re.I),
        re.compile(r"\bcron(tab)?\b", re.I),
    ],
}


class CapabilityPermissions:
    """Loads and evaluates capability-level permission rules from permissions.yaml."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._capabilities: dict[str, dict] = config.get("capabilities", {})

    @classmethod
    def load(cls, path: str, auto_create: bool = True) -> "CapabilityPermissions":
        """Load permissions from *path*, creating a default file if absent."""
        try:
            import yaml  # PyYAML is a transitive dependency
        except ImportError:
            logger.warning(
                "PyYAML not available — extended permissions disabled. "
                "Install with: pip install pyyaml"
            )
            return cls({})

        p = Path(path).expanduser().resolve()

        if not p.exists():
            if auto_create:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(_DEFAULT_YAML, encoding="utf-8")
                logger.info("Created default permissions file: %s", p)
            else:
                logger.info("Permissions file not found, using permissive defaults: %s", p)
                return cls({})

        try:
            with p.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            logger.info("Loaded extended permissions from %s", p)
            return cls(data)
        except Exception as exc:
            logger.error("Failed to parse permissions.yaml (%s): %s — using defaults", p, exc)
            return cls({})

    def check_command(self, command: str) -> tuple[bool, str]:
        """Return (allowed, reason) for the given shell command.

        Checks which capability category the command falls into and whether
        that category is enabled.  Commands that don't match any category
        are allowed by default.
        """
        if not self._capabilities:
            # No capability rules loaded — allow everything
            return True, ""

        stripped = command.strip()
        for category, patterns in _CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(stripped):
                    cap_config = self._capabilities.get(category, {})
                    enabled = cap_config.get("enabled", True)
                    if not enabled:
                        reason = (
                            f"capability '{category}' is disabled in "
                            "~/.steelclaw/permissions.yaml"
                        )
                        logger.warning(
                            "Command blocked by capability rule [%s]: %s", category, stripped[:80]
                        )
                        return False, reason

                    # Extra check: package managers whitelist
                    if category == "packages":
                        allowed_managers = cap_config.get("managers", [])
                        if allowed_managers:
                            cmd_lower = stripped.lower()
                            if not any(mgr in cmd_lower for mgr in allowed_managers):
                                return (
                                    False,
                                    f"package manager not in allowed list: {allowed_managers}",
                                )

                    # Extra check: filesystem path restrictions
                    if category == "filesystem":
                        allowed_paths = cap_config.get("allowed_paths", [])
                        if allowed_paths:
                            allowed, reason = self._check_filesystem_paths(
                                stripped, allowed_paths
                            )
                            if not allowed:
                                return False, reason

                    return True, ""

        # No category matched — allow by default
        return True, ""

    def _check_filesystem_paths(
        self, command: str, allowed_paths: list[str]
    ) -> tuple[bool, str]:
        """Verify that any absolute paths referenced in the command are within allowed_paths."""
        expanded = [str(Path(p).expanduser().resolve()) for p in allowed_paths]
        # Find path-like tokens in the command
        tokens = re.findall(r"(?:^|\s)((?:/|~)[^\s;|&>]+)", command)
        for token in tokens:
            resolved = str(Path(token).expanduser().resolve())
            if not any(resolved.startswith(ap) for ap in expanded):
                return (
                    False,
                    f"filesystem path '{token}' is outside allowed_paths",
                )
        return True, ""

    def is_category_enabled(self, category: str) -> bool:
        """Return True if the named capability category is enabled."""
        return self._capabilities.get(category, {}).get("enabled", True)
