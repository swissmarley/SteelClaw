"""Security commands for managing approval rules and permissions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from steelclaw.paths import PROJECT_ROOT


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
    """Save approval rules to file."""
    path = _get_approvals_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


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
    if permission not in ("ask", "record", "ignore"):
        print(f"Invalid permission: {permission}. Must be ask, record, or ignore.")
        return

    # Update config.json
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    if "agents" not in config:
        config["agents"] = {}
    if "security" not in config["agents"]:
        config["agents"]["security"] = {}
    config["agents"]["security"]["default_permission"] = permission
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))

    print(f"Set default permission to: {permission}")


def _sudo_enable(value: str) -> None:
    """Enable or disable sudo mode."""
    if value.lower() not in ("true", "false"):
        print("Value must be 'true' or 'false'")
        return

    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    if "security" not in config:
        config["security"] = {}
    if "sudo" not in config["security"]:
        config["security"]["sudo"] = {}
    config["security"]["sudo"]["enabled"] = value.lower() == "true"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2))

    print(f"Sudo mode: {value}")


def _sudo_whitelist(action: str, pattern: str | None) -> None:
    """Manage sudo whitelist."""
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    if "security" not in config:
        config["security"] = {}
    if "sudo" not in config["security"]:
        config["security"]["sudo"] = {"enabled": False, "whitelist": []}
    if "whitelist" not in config["security"]["sudo"]:
        config["security"]["sudo"]["whitelist"] = []

    whitelist = config["security"]["sudo"]["whitelist"]

    if action == "list":
        if whitelist:
            print("Sudo whitelist:")
            for p in whitelist:
                print(f"  {p}")
        else:
            print("Sudo whitelist is empty")
    elif action == "add":
        if pattern:
            if pattern not in whitelist:
                whitelist.append(pattern)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(json.dumps(config, indent=2))
                print(f"Added to sudo whitelist: {pattern}")
            else:
                print(f"Pattern already in whitelist: {pattern}")
        else:
            print("Pattern required for add")
    elif action == "remove":
        if pattern:
            if pattern in whitelist:
                whitelist.remove(pattern)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(json.dumps(config, indent=2))
                print(f"Removed from sudo whitelist: {pattern}")
            else:
                print(f"Pattern not in whitelist: {pattern}")
        else:
            print("Pattern required for remove")


def _show_capabilities() -> None:
    """Show capability permissions."""
    import yaml

    perm_path = _get_permissions_path()
    if not perm_path.exists():
        print("No capabilities configured.")
        print(f"Create {perm_path} to configure capability permissions.")
        return

    content = perm_path.read_text()
    try:
        data = yaml.safe_load(content)
        print("Capability Permissions:")
        print(yaml.dump(data, default_flow_style=False))
    except Exception as e:
        print(f"Error reading permissions: {e}")


def _set_capability(name: str, value: str) -> None:
    """Set a capability permission."""
    import yaml

    perm_path = _get_permissions_path()
    perm_path.parent.mkdir(parents=True, exist_ok=True)

    if perm_path.exists():
        content = perm_path.read_text()
        try:
            data = yaml.safe_load(content) or {}
        except Exception:
            data = {}
    else:
        data = {}

    # Parse value
    if value.lower() in ("true", "yes", "allow"):
        data[name] = True
    elif value.lower() in ("false", "no", "deny"):
        data[name] = False
    else:
        print(f"Invalid value: {value}. Use true/false, yes/no, or allow/deny")
        return

    perm_path.write_text(yaml.dump(data, default_flow_style=False))
    print(f"Set capability {name} = {data[name]}")