"""Security commands for managing approval rules and permissions."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from steelclaw.paths import PROJECT_ROOT


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON data to file atomically.

    Uses a temp file and os.replace to ensure atomic writes,
    preventing data corruption if interrupted mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write YAML data to file atomically.

    Uses a temp file and os.replace to ensure atomic writes,
    preventing data corruption if interrupted mid-write.
    """
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(data, default_flow_style=False)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def handle_security(args: argparse.Namespace) -> None:
    """Handle security commands."""
    action = args.security_action

    if action == "show":
        _show_security()
    elif action == "list-rules":
        _list_rules()
    elif action == "add-rule":
        _add_rule(args.pattern, args.permission, args.note)
    elif action == "remove-rule":
        _remove_rule(args.pattern)
    elif action == "set-default":
        _set_default(args.permission)
    elif action == "sudo-enable":
        _sudo_enable(args.value)
    elif action == "sudo-whitelist":
        _sudo_whitelist(args.action, args.pattern)
    elif action == "capabilities":
        _show_capabilities()
    elif action == "set-capability":
        _set_capability(args.name, args.value)
    else:
        print(f"Unknown security action: {action}")


def _get_approvals_path() -> Path:
    """Get the path to exec-approvals.json."""
    return PROJECT_ROOT / "exec-approvals.json"


def _get_permissions_path() -> Path:
    """Get the path to permissions.yaml."""
    return Path.home() / ".steelclaw" / "permissions.yaml"


def _load_approvals() -> dict:
    """Load approval rules from file."""
    path = _get_approvals_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"version": 1, "rules": []}


def _save_approvals(data: dict) -> None:
    """Save approval rules to file atomically.

    Uses a temp file and os.replace to ensure atomic writes,
    preventing data corruption if interrupted mid-write.
    """
    import os
    import tempfile

    path = _get_approvals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2)

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _show_security() -> None:
    """Show all security settings."""
    print("=== Security Settings ===\n")

    # Show approval rules
    print("Approval Rules (exec-approvals.json):")
    approvals = _load_approvals()
    if approvals.get("rules"):
        for rule in approvals["rules"]:
            print(f"  {rule.get('permission', 'ask'):8} {rule.get('pattern', '')}")
            if rule.get("note"):
                print(f"           Note: {rule['note']}")
    else:
        print("  (no rules defined)")

    # Show permissions.yaml if exists
    perm_path = _get_permissions_path()
    if perm_path.exists():
        print(f"\nCapability Permissions ({perm_path}):")
        print(perm_path.read_text())
    else:
        print("\n  (no permissions.yaml)")


def _list_rules() -> None:
    """List all approval rules."""
    approvals = _load_approvals()
    rules = approvals.get("rules", [])

    if not rules:
        print("No approval rules defined.")
        return

    print(f"{'Permission':<10} {'Pattern':<30} Note")
    print("-" * 60)
    for rule in rules:
        perm = rule.get("permission", "ask")
        pattern = rule.get("pattern", "")
        note = rule.get("note", "")
        print(f"{perm:<10} {pattern:<30} {note}")


def _add_rule(pattern: str, permission: str, note: str | None) -> None:
    """Add an approval rule."""
    if permission not in ("ask", "record", "ignore"):
        print(f"Invalid permission: {permission}. Must be ask, record, or ignore.")
        return

    from datetime import datetime, timezone

    approvals = _load_approvals()

    # Remove existing rule with same pattern
    approvals["rules"] = [r for r in approvals.get("rules", []) if r.get("pattern") != pattern]

    approvals["rules"].append({
        "pattern": pattern,
        "permission": permission,
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "note": note or "",
    })

    _save_approvals(approvals)
    print(f"Added rule: {permission} {pattern}")


def _remove_rule(pattern: str) -> None:
    """Remove an approval rule."""
    approvals = _load_approvals()
    before = len(approvals.get("rules", []))
    approvals["rules"] = [r for r in approvals.get("rules", []) if r.get("pattern") != pattern]

    if len(approvals["rules"]) < before:
        _save_approvals(approvals)
        print(f"Removed rule: {pattern}")
    else:
        print(f"Rule not found: {pattern}")


def _set_default(permission: str) -> None:
    """Set the default permission level."""
    import os
    import tempfile

    if permission not in ("ask", "record", "ignore"):
        print(f"Invalid permission: {permission}. Must be ask, record, or ignore.")
        return

    # Update config.json atomically
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    # Ensure proper nesting under agents.security
    if "agents" not in config:
        config["agents"] = {}
    if "security" not in config["agents"]:
        config["agents"]["security"] = {}
    config["agents"]["security"]["default_permission"] = permission

    # Atomic write
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(config, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, config_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"Set default permission to: {permission}")


def _sudo_enable(value: str) -> None:
    """Enable or disable sudo mode."""
    import os
    import tempfile

    if value.lower() not in ("true", "false"):
        print("Value must be 'true' or 'false'")
        return

    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    # Ensure proper nesting under agents.security.sudo
    if "agents" not in config:
        config["agents"] = {}
    if "security" not in config["agents"]:
        config["agents"]["security"] = {}
    if "sudo" not in config["agents"]["security"]:
        config["agents"]["security"]["sudo"] = {}
    config["agents"]["security"]["sudo"]["enabled"] = value.lower() == "true"

    # Atomic write
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(config, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, config_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    print(f"Sudo mode: {value}")


def _sudo_whitelist(action: str, pattern: str | None) -> None:
    """Manage sudo whitelist."""
    import os
    import tempfile

    def _save_config_atomic(config: dict, config_path: Path) -> None:
        """Save config atomically using temp file + os.replace."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(config, indent=2)
        fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_path, config_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    # Ensure proper nesting under agents.security.sudo
    if "agents" not in config:
        config["agents"] = {}
    if "security" not in config["agents"]:
        config["agents"]["security"] = {}
    if "sudo" not in config["agents"]["security"]:
        config["agents"]["security"]["sudo"] = {"enabled": False, "whitelist": []}
    if "whitelist" not in config["agents"]["security"]["sudo"]:
        config["agents"]["security"]["sudo"]["whitelist"] = []

    whitelist = config["agents"]["security"]["sudo"]["whitelist"]

    if action == "list":
        if whitelist:
            print("Sudo whitelist:")
            for p in whitelist:
                print(f"  {p}")
        else:
            print("Sudo whitelist is empty.")
    elif action == "add":
        if not pattern:
            print("Pattern is required for 'add' action.")
            return
        if pattern not in whitelist:
            whitelist.append(pattern)
            _save_config_atomic(config, config_path)
            print(f"Added to whitelist: {pattern}")
        else:
            print(f"Pattern already in whitelist: {pattern}")
    elif action == "remove":
        if not pattern:
            print("Pattern is required for 'remove' action.")
            return
        if pattern in whitelist:
            whitelist.remove(pattern)
            _save_config_atomic(config, config_path)
            print(f"Removed from whitelist: {pattern}")
        else:
            print(f"Pattern not found in whitelist: {pattern}")
    else:
        print(f"Unknown whitelist action: {action}")


def _show_capabilities() -> None:
    """Show capability permissions from permissions.yaml."""
    perm_path = _get_permissions_path()
    if perm_path.exists():
        print(perm_path.read_text())
    else:
        print("No permissions.yaml found.")
        print(f"Expected location: {perm_path}")


def _set_nested_value(data: dict, path: str, value) -> None:
    """Set a nested value in a dict using dot-notation path.

    Creates intermediate dicts as needed. Supports paths like
    'capabilities.filesystem.enabled'.
    """
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _set_capability(name: str, value: str) -> None:
    """Set a capability permission in permissions.yaml.

    Supports dot-notation for nested keys (e.g., filesystem.enabled).
    """
    import yaml

    perm_path = _get_permissions_path()

    # Load existing permissions or start fresh
    if perm_path.exists():
        try:
            content = perm_path.read_text(encoding="utf-8")
            perms = yaml.safe_load(content) or {}
        except (IOError, yaml.YAMLError) as e:
            print(f"Error reading permissions.yaml: {e}")
            perms = {}
    else:
        perms = {}

    # Ensure capabilities section exists
    if "capabilities" not in perms:
        perms["capabilities"] = {}

    # Parse value
    try:
        # Try to parse as JSON (handles bool, int, null)
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        # Handle common string values
        val_lower = value.lower()
        if val_lower in ("true", "yes", "allow"):
            parsed_value = True
        elif val_lower in ("false", "no", "deny"):
            parsed_value = False
        else:
            parsed_value = value  # Keep as string

    # Set the capability using dot notation
    _set_nested_value(perms["capabilities"], name, parsed_value)

    # Write atomically
    try:
        _atomic_write_yaml(perm_path, perms)
        print(f"✓ Set capability: {name} = {json.dumps(parsed_value)}")
    except Exception as e:
        print(f"Error saving permissions.yaml: {e}")
