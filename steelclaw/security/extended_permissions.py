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

# Default permissions.yaml template written when the file is absent.
# NOTE: Sudo settings are configured separately in config.json under
# "agents.security.sudo".  They are NOT read from this file.
_DEFAULT_YAML = """\
# SteelClaw — Extended Capability Permissions
# Toggle each capability category on or off. Changes take effect on restart.
# See docs for details on each category.
#
# NOTE: Sudo settings (enabled, whitelist, audit_log) are configured in
# config.json under agents.security.sudo — not here.

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
"""

# Shell operator tokens that shlex returns as standalone tokens.
# These are used to split a tokenised command list into per-subcommand slices.
_CHAIN_OPS = frozenset({"&&", "||", ";", "|"})

# Regex for simple backtick subshells (no nesting possible in backticks)
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _extract_dollar_subshells(command: str) -> list[str]:
    """Extract all $() subshell contents using balanced parenthesis counting.

    This properly handles nested subshells like $(echo $(ls)) by counting
    parentheses to find matching pairs. Returns a list of inner command strings.
    """
    results: list[str] = []
    i = 0
    while i < len(command):
        # Look for $(
        if command[i : i + 2] == "$(":
            start = i + 2  # Position after "$("
            depth = 1
            j = start
            # Count balanced parentheses to find the matching close
            while j < len(command) and depth > 0:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                # Found matching close parenthesis
                inner = command[start : j - 1].strip()
                if inner:
                    results.append(inner)
                i = j  # Continue after the closing ')'
                continue
        i += 1
    return results

# Mapping from capability category to executable-name patterns.
# These match against the *first token* of each subcommand (the executable),
# after the command string has been split on shell chain operators and parsed
# with shlex.
_CATEGORY_EXECUTABLES: dict[str, list[re.Pattern]] = {
    "filesystem": [
        re.compile(r"^(rm|mv|cp|cat|tee|truncate|touch|mkdir|rmdir|chmod|chown|find|locate|ls|dir)$", re.I),
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


def _split_into_subcommands(command: str) -> list[str]:
    """Split a shell command string into individual subcommands.

    Two-phase approach that handles both issues together:

    **Phase 1 – Subshell extraction:** ``$(...)`` and backtick constructs are
    located in the *raw* string using balanced parenthesis counting for $()
    (handles nesting) and regex for backticks (no nesting possible).  Their
    inner content is recursively split and appended to the result.  The
    constructs are then replaced with a placeholder so the outer command can
    be cleanly tokenised.  This prevents a subshell like
    ``echo $(curl evil.com)`` from hiding ``curl`` inside ``echo``'s
    argument list.

    **Phase 2 – Operator-aware tokenisation:** The placeholder-substituted
    outer command is tokenised with ``shlex.split()``, which respects quoted
    strings.  Any operator token (``&&``, ``||``, ``;``, ``|``) in the
    resulting list marks a subcommand boundary.  This prevents a command like
    ``git commit -m "fix; issue"`` from being incorrectly split on the ``;``
    inside the quoted message.
    """
    result: list[str] = []

    # Phase 1: extract subshell commands from raw string before shlex.
    # Handle $() subshells with balanced parenthesis counting (supports nesting)
    for inner in _extract_dollar_subshells(command):
        result.extend(_split_into_subcommands(inner))

    # Handle backtick subshells (no nesting possible)
    for m in _BACKTICK_RE.finditer(command):
        inner = (m.group(1) or "").strip()
        if inner:
            result.extend(_split_into_subcommands(inner))

    # Replace subshell constructs with a neutral placeholder so shlex can
    # tokenise the outer command without hitting unbalanced-paren errors.
    # Use a function-based replacement for $() to handle nested cases properly.
    def replace_dollar_parens(s: str) -> str:
        result_str = []
        i = 0
        while i < len(s):
            if s[i : i + 2] == "$(":
                depth = 1
                j = i + 2
                while j < len(s) and depth > 0:
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                    j += 1
                result_str.append(" __subshell__ ")
                i = j
            else:
                result_str.append(s[i])
                i += 1
        return "".join(result_str)

    outer = replace_dollar_parens(command)
    outer = _BACKTICK_RE.sub(" __subshell__ ", outer)

    # Phase 2: shlex-tokenise to respect quoted strings, then split on operators.
    try:
        tokens = shlex.split(outer)
    except ValueError:
        # Malformed quoting — fall back to simple whitespace split (less precise)
        tokens = outer.split()

    current: list[str] = []
    for token in tokens:
        if token in _CHAIN_OPS:
            if current:
                result.append(" ".join(current))
                current = []
        elif token != "__subshell__":
            current.append(token)

    if current:
        result.append(" ".join(current))

    return result if result else [command.strip()]


def _has_redirect_operator(command: str) -> bool:
    """Return True if the command contains a shell output-redirect operator.

    Uses ``shlex.split()`` to tokenise so that ``>`` inside a quoted string
    (e.g. ``echo "Value > 10"``) does not produce a false positive.  Falls
    back to a simple regex scan if tokenisation fails (e.g. unbalanced quotes).
    """
    try:
        tokens = shlex.split(command)
        # shlex returns '>' as a standalone token and '>file' as a single token
        # starting with '>'.  Both indicate a redirect operator.
        return any(t == ">" or t == ">>" or t.startswith(">") for t in tokens)
    except ValueError:
        # Fallback: regex on raw string (may produce false positives for broken input)
        return bool(re.search(r">\s*\S", command))


class CapabilityPermissions:
    """Loads and evaluates capability-level permission rules from permissions.yaml."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._capabilities: dict[str, dict] = config.get("capabilities", {})
        # Pre-resolve allowed_paths for each category once at construction time
        # to avoid repeated filesystem calls on every check_command invocation.
        self._resolved_allowed_paths: dict[str, list[Path]] = {}
        for cat, cap_cfg in self._capabilities.items():
            paths = cap_cfg.get("allowed_paths", [])
            if paths:
                self._resolved_allowed_paths[cat] = [
                    Path(p).expanduser().resolve() for p in paths
                ]

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

        The command is split into individual subcommands respecting shell chain
        operators and quoted strings (see ``_split_into_subcommands``).  Each
        subcommand's executable is matched against category patterns.

        Commands that don't match any category are allowed by default.
        """
        if not self._capabilities:
            return True, ""

        raw = command.strip()

        # Check redirect operator using shlex-aware detection (avoids false
        # positives for '>' inside quoted strings like echo "Value > 10").
        fs_config = self._capabilities.get("filesystem", {})
        if not fs_config.get("enabled", True):
            if _has_redirect_operator(raw):
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
            tokens = subcmd.split()

        if not tokens:
            return True, ""

        executable = tokens[0].lstrip("-")
        executable_name = os.path.basename(executable)

        for exec_key, patterns in _CATEGORY_EXECUTABLES.items():
            category = exec_key  # keys are the same as category names now
            for pattern in patterns:
                if pattern.match(executable_name):
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

                    # Extra check: filesystem path restrictions (uses pre-resolved paths)
                    if category == "filesystem":
                        resolved_allowed = self._resolved_allowed_paths.get(category, [])
                        if resolved_allowed:
                            ok, reason = self._check_filesystem_paths(tokens[1:], resolved_allowed)
                            if not ok:
                                return False, reason

                    return True, ""

        return True, ""

    def _check_filesystem_paths(
        self, arg_tokens: list[str], resolved_allowed: list[Path]
    ) -> tuple[bool, str]:
        """Verify that path arguments are within the configured allowed_paths.

        Uses pre-resolved ``Path`` objects (computed once in ``__init__``) and
        ``Path.is_relative_to()`` for correct prefix matching.

        Every non-flag token is resolved so that bare filenames like
        ``secret.txt`` (which become ``<cwd>/secret.txt``) are caught too.
        """
        for token in arg_tokens:
            if token.startswith("-"):
                continue  # skip option flags
            try:
                resolved = Path(token).expanduser().resolve()
            except Exception:
                continue

            if not any(_is_relative_to(resolved, allowed) for allowed in resolved_allowed):
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
        parent_str = str(parent)
        path_str = str(path)
        return path_str == parent_str or path_str.startswith(parent_str + os.sep)
