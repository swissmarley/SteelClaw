"""Command approval persistence — exec-approvals.json management."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("steelclaw.security.approvals")


class ApprovalStore:
    """Persists command approvals so the user isn't asked twice for the same safe command.

    Format of exec-approvals.json:
    {
        "version": 1,
        "rules": [
            {
                "pattern": "git *",
                "permission": "ignore",
                "granted_at": "2026-03-26T12:00:00Z",
                "note": "All git commands auto-approved"
            }
        ]
    }
    """

    def __init__(self, file_path: str = "exec-approvals.json") -> None:
        self._path = Path(file_path)
        self._rules: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._rules = data.get("rules", [])
                logger.info("Loaded %d approval rules from %s", len(self._rules), self._path)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Invalid approvals file %s — starting fresh", self._path)
                self._rules = []
        else:
            self._rules = []

    def _save(self) -> None:
        data = {
            "version": 1,
            "rules": self._rules,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def check(self, command: str) -> str | None:
        """Check if a command matches any existing approval rule.

        Returns the permission level ("ask", "record", "ignore") or None if no match.
        """
        for rule in self._rules:
            pattern = rule.get("pattern", "")
            if fnmatch(command, pattern) or command == pattern:
                return rule.get("permission", "ask")
        return None

    def add_rule(
        self,
        pattern: str,
        permission: str = "ignore",
        note: str = "",
    ) -> None:
        """Add a new approval rule with glob pattern matching."""
        if permission not in ("ask", "record", "ignore"):
            raise ValueError(f"Invalid permission: {permission}. Must be ask, record, or ignore.")

        # Remove existing rules with the same pattern
        self._rules = [r for r in self._rules if r.get("pattern") != pattern]

        self._rules.append({
            "pattern": pattern,
            "permission": permission,
            "granted_at": datetime.now(timezone.utc).isoformat(),
            "note": note,
        })
        self._save()
        logger.info("Added approval rule: %s → %s", pattern, permission)

    def remove_rule(self, pattern: str) -> bool:
        """Remove a rule by pattern. Returns True if found and removed."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.get("pattern") != pattern]
        if len(self._rules) < before:
            self._save()
            return True
        return False

    def list_rules(self) -> list[dict]:
        return list(self._rules)

    def clear(self) -> None:
        self._rules = []
        self._save()
