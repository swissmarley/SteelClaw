"""Extended capability-level permission system backed by ~/.steelclaw/permissions.yaml.

Provides granular, category-based toggles (filesystem, processes, network,
packages, environment, cron) that layer on top of the existing three-tier
command approval model.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
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

# Shell operator tokens that separate independent subcommands.
# We split the full pipeline on these so that chained commands like
# "ls && curl ..." are each checked against capability rules.
_CHAIN_SPLIT_RE = re.compile(r"&&|\|\|?|;")

# Mapping from capability category to executable-name patterns.
# These match against the *first token* of each subcommand (the executable),
# after the command string has been split on shell chain operators and parsed
# with shlex.  Using word-boundary anchors on the full first-token avoids the
# ^ bypass via prepended spaces or subshell wrappers.
_CATEGORY_EXECUTABLES: dict[str, list[re.Pattern]] = {
    "filesystem": [
        re.compile(r"^(rm|mv|cp|cat|tee|truncate|touch|mkdir|rmdir|chmod|chown|find|locate|ls|dir)$", re.I),
    ],
    "filesystem_redirect": [
        # Output-redirect operator anywhere in the raw command string
        re.compile(r">\s*\S"),
    ],
    "processes": [
        re.compile(r"^(kill|pkill|killall|systemctl|service|supervisorctl|launchctl)$", re.I),
    ],
    "network": [
        re.compile(r"^(curl|wget|nc|ncat|netcat|nmap|ssh|scp|rsync|ftp|sftp|dig|host|nslookup|ping|traceroute|tracepath|mtr|ifconfig|netstat|ss)$", re.I),
        re.compile(r"^ip$", re.I),  # "ip addr", "ip route", etc.
    ],
    "packages": [
        re.compile(r"^pip\d*$", re.I),
        re.compile(r"^(apt-get|apt|dpkg)$", re.I),
        re.compile(r"^brew$", re.I),
        re.compile(r"^npm$", re.I),
        re.compile(r"^(yarn|pnpm)$", re.I),
    ],
    "environment": [
        re.compile(r"^(export|unset|env|printenv|set)$", re.I),
        re.compile(r"\.env$", re.I),  # match ".env" file token
    ],
    "cron": [
        re.compile(r"^(crontab|at|batch|anacron)$", re.I),
    ],
}

# Map the internal keys back to the user-facing capability category names
_EXEC_TO_CATEGORY = {
    "filesystem": "filesystem",
    "filesystem_redirect": "filesystem",
    "processes": "processes",
    "network": "network",
    "packages": "packages",
    "environment": "environment",
    "cron": "cron",
}


def _split_into_subcommands(command: str) -> list[str]:
    """Split a shell command string into individual subcommands.

    Handles ``&&``, ``||``, ``;``, and ``|`` pipeline operators as well as
    subshell constructs ``$(...)`` and ``(...)`` by stripping the wrappers so
    each token can be examined independently.
    """
    # Remove subshell wrappers so "$(curl ...)" → "curl ..."
    cleaned = re.sub(r"\$\(", " ", command)
    cleaned = re.sub(r"\(", " ", cleaned)
    cleaned = re.sub(r"\)", " ", cleaned)

    parts = _CHAIN_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


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

        The command is split into individual subcommands on shell chain
        operators (``&&``, ``||``, ``;``, ``|``) and subshell constructs
        (``$(...)``, ``(...)``).  Each subcommand's first token (the
        executable) is matched against category patterns.  This prevents
        bypasses via command chaining or subshells.

        Commands that don't match any category are allowed by default.
        """
        if not self._capabilities:
            return True, ""

        raw = command.strip()

        # Check redirect operator at the whole-command level (filesystem)
        fs_config = self._capabilities.get("filesystem", {})
        if not fs_config.get("enabled", True):
            for pattern in _CATEGORY_EXECUTABLES.get("filesystem_redirect", []):
                if pattern.search(raw):
                    reason = "capability 'filesystem' is disabled in ~/.steelclaw/permissions.yaml"
                    logger.warning("Command blocked by capability rule [filesystem/redirect]: %s", raw[:80])
                    return False, reason

        # Split into subcommands and check each executable token
        subcommands = _split_into_subcommands(raw)
        for subcmd in subcommands:
            allowed, reason = self._check_subcommand(subcmd, raw)
            if not allowed:
                return False, reason

        return True, ""

    def _check_subcommand(self, subcmd: str, full_command: str) -> tuple[bool, str]:
        """Check a single subcommand (after chain-splitting) against capability rules."""
        # Parse the subcommand with shlex to get the executable token safely
        try:
            tokens = shlex.split(subcmd)
        except ValueError:
            # Malformed quoting — fall back to simple whitespace split
            tokens = subcmd.split()

        if not tokens:
            return True, ""

        executable = tokens[0].lstrip("-")  # strip leading dashes (e.g. from --option leaks)

        for exec_key, patterns in _CATEGORY_EXECUTABLES.items():
            category = _EXEC_TO_CATEGORY[exec_key]
            if exec_key == "filesystem_redirect":
                continue  # handled at whole-command level above

            for pattern in patterns:
                if pattern.match(executable):
                    cap_config = self._capabilities.get(category, {})
                    enabled = cap_config.get("enabled", True)
                    if not enabled:
                        reason = (
                            f"capability '{category}' is disabled in "
                            "~/.steelclaw/permissions.yaml"
                        )
                        logger.warning(
                            "Command blocked by capability rule [%s]: %s",
                            category, full_command[:80],
                        )
                        return False, reason

                    # Extra check: package managers whitelist
                    if category == "packages":
                        allowed_managers = cap_config.get("managers", [])
                        if allowed_managers:
                            if not any(
                                executable.lower().startswith(mgr.lower())
                                for mgr in allowed_managers
                            ):
                                return (
                                    False,
                                    f"package manager not in allowed list: {allowed_managers}",
                                )

                    # Extra check: filesystem path restrictions
                    if category == "filesystem":
                        allowed_paths = cap_config.get("allowed_paths", [])
                        if allowed_paths:
                            ok, reason = self._check_filesystem_paths(tokens[1:], allowed_paths)
                            if not ok:
                                return False, reason

                    return True, ""

        return True, ""

    def _check_filesystem_paths(
        self, arg_tokens: list[str], allowed_paths: list[str]
    ) -> tuple[bool, str]:
        """Verify that path arguments are within the configured allowed_paths.

        Uses ``Path.is_relative_to()`` (Python 3.9+) for correct prefix
        matching, preventing ``/home/user_backup`` from matching ``/home/user``.

        Every non-flag token is resolved (bare names like ``secret.txt`` become
        ``<cwd>/secret.txt``) so that commands like ``cat etc/passwd`` are
        caught even when they don't start with ``/``, ``~``, ``./``, or ``../``.

        Args:
            arg_tokens: Already-shlex-parsed argument tokens (not the executable).
            allowed_paths: List of allowed path strings from the config.
        """
        expanded_allowed = [
            Path(p).expanduser().resolve() for p in allowed_paths
        ]

        for token in arg_tokens:
            # Skip option flags (e.g. -r, --recursive)
            if token.startswith("-"):
                continue
            # Resolve ALL non-flag tokens — bare filenames (e.g. "secret.txt",
            # "etc/passwd") are resolved relative to the current working directory.
            try:
                resolved = Path(token).expanduser().resolve()
            except Exception:
                continue

            if not any(
                _is_relative_to(resolved, allowed) for allowed in expanded_allowed
            ):
                return (
                    False,
                    f"filesystem path '{token}' is outside allowed_paths",
                )
        return True, ""

    def is_category_enabled(self, category: str) -> bool:
        """Return True if the named capability category is enabled."""
        return self._capabilities.get(category, {}).get("enabled", True)


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Return True if *path* is equal to or under *parent*.

    Uses ``Path.is_relative_to()`` on Python 3.9+ and falls back to a
    safe string comparison that appends ``os.sep`` to avoid
    ``/home/user_backup`` matching ``/home/user``.
    """
    try:
        return path.is_relative_to(parent)
    except AttributeError:
        # Python < 3.9 fallback
        parent_str = str(parent)
        path_str = str(path)
        return path_str == parent_str or path_str.startswith(parent_str + os.sep)
