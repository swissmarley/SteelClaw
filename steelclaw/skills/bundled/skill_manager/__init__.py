"""Skill Manager — runtime skill lifecycle management tool."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("steelclaw.skills.skill_manager")

# ── Module-level registry reference (injected by app.py) ─────────────────────

_skill_registry = None
_global_skills_dir: str = "~/.steelclaw/skills"
_workspace_skills_dir: str = ".steelclaw/skills"


def _set_registry(registry, global_dir: str = "", workspace_dir: str = "") -> None:
    """Called by app startup to inject the live skill registry."""
    global _skill_registry, _global_skills_dir, _workspace_skills_dir
    _skill_registry = registry
    if global_dir:
        _global_skills_dir = global_dir
    if workspace_dir:
        _workspace_skills_dir = workspace_dir


# ── Tool functions ────────────────────────────────────────────────────────────


async def tool_list_skills() -> str:
    """List all currently loaded skills with metadata."""
    if _skill_registry is None:
        return "Error: skill registry not available"

    skills = _skill_registry.list_skills()
    if not skills:
        return "No skills currently loaded."

    rows = []
    for skill in skills:
        meta = skill.metadata
        enabled = "enabled" if skill.default_enabled else "disabled"
        rows.append(
            f"- **{meta.name}** [{skill.scope}] [{enabled}]\n"
            f"  {meta.description or '(no description)'}"
        )

    return f"## Loaded Skills ({len(skills)})\n\n" + "\n".join(rows)


async def tool_create_skill(
    name: str,
    description: str,
    tools_spec: str = "",
) -> str:
    """Scaffold a new skill in the global skills directory.

    Args:
        name: Snake-case skill directory name (e.g. my_skill).
        description: One-sentence description of the skill.
        tools_spec: Optional JSON array of tool specs.
    """
    # Sanitise name
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")
    if not safe_name:
        return "Error: invalid skill name"

    skill_dir = Path(_global_skills_dir).expanduser().resolve() / safe_name

    if skill_dir.exists():
        return f"Error: skill '{safe_name}' already exists at {skill_dir}"

    # Build SKILL.md content
    tools_section = _build_tools_section(tools_spec)
    skill_md = f"""# {safe_name.replace("_", " ").title()}

{description}

## Metadata
- version: 0.1.0
- author: user

## System Prompt
You are a specialist assistant for {description.rstrip(".").lower()}.

## Tools
{tools_section}
"""

    # Build __init__.py content — sanitize every tool name before embedding in Python source
    tool_names = _extract_tool_names(tools_spec, safe_name)
    init_lines = ['"""Auto-scaffolded skill: ' + safe_name + '."""', "", "from __future__ import annotations", ""]
    for raw_tool_name in tool_names:
        # Re-sanitize here even though _extract_tool_names already does it, as a
        # defence-in-depth safeguard before injecting into generated Python source.
        tool_name = re.sub(r"[^a-z0-9_]", "_", raw_tool_name.lower().strip()).strip("_") or "run"
        init_lines += [
            f"",
            f"async def tool_{tool_name}(input: str) -> str:",
            f'    """Execute {tool_name.replace("_", " ")}."""',
            f"    # TODO: implement this tool",
            f'    return f"tool_{tool_name} called with: {{input}}"',
        ]

    init_py = "\n".join(init_lines) + "\n"

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (skill_dir / "__init__.py").write_text(init_py, encoding="utf-8")
        return (
            f"Skill '{safe_name}' created at {skill_dir}\n"
            f"Run `reload_skills` to activate it, then edit __init__.py to implement the tools."
        )
    except Exception as exc:
        return f"Error creating skill '{safe_name}': {exc}"


async def tool_edit_skill(
    name: str,
    file: str,
    content: str,
) -> str:
    """Replace a skill file (SKILL.md or __init__.py).

    Args:
        name: Skill directory name.
        file: "SKILL.md" or "__init__.py".
        content: New complete file content.
    """
    if file not in ("SKILL.md", "__init__.py"):
        return "Error: file must be 'SKILL.md' or '__init__.py'"

    # Sanitise name to prevent path traversal (e.g. "../../etc")
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")
    if not safe_name:
        return "Error: invalid skill name"

    # Try global first, then workspace
    for scope_dir in (
        Path(_global_skills_dir).expanduser(),
        Path(_workspace_skills_dir).expanduser(),
    ):
        base = scope_dir.resolve()
        skill_dir = (base / safe_name).resolve()
        # Ensure the resolved path is actually inside the expected base (defence-in-depth)
        # Use is_relative_to for robust path validation (Python 3.9+)
        try:
            if not skill_dir.is_relative_to(base):
                return "Error: invalid skill path"
        except (ValueError, RuntimeError):
            return "Error: invalid skill path"
        target = skill_dir / file
        if skill_dir.exists():
            if target.exists() or file == "SKILL.md":
                target.write_text(content, encoding="utf-8")
                return f"Updated {target}\nRun `reload_skills` to apply changes."

    return (
        f"Error: skill '{safe_name}' not found in global or workspace directories. "
        "Bundled skills cannot be edited."
    )


async def tool_delete_skill(
    name: str,
    scope: str = "global",
) -> str:
    """Delete a skill from the global or workspace directory.

    Args:
        name: Skill directory name to delete.
        scope: "global" (default) or "workspace".
    """
    # Sanitise name to prevent path traversal (e.g. "../../etc")
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")
    if not safe_name:
        return "Error: invalid skill name"

    if scope == "global":
        base = Path(_global_skills_dir).expanduser().resolve()
    elif scope == "workspace":
        base = Path(_workspace_skills_dir).expanduser().resolve()
    else:
        return f"Error: scope must be 'global' or 'workspace', got '{scope}'"

    skill_dir = (base / safe_name).resolve()
    # Ensure the resolved path is actually inside the expected base (defence-in-depth)
    # Use is_relative_to for robust path validation (Python 3.9+)
    try:
        if not skill_dir.is_relative_to(base):
            return "Error: invalid skill path"
    except (ValueError, RuntimeError):
        return "Error: invalid skill path"

    if not skill_dir.exists():
        return f"Error: skill '{safe_name}' not found at {skill_dir}"

    try:
        shutil.rmtree(skill_dir)
        return f"Skill '{safe_name}' deleted from {skill_dir}\nRun `reload_skills` to apply."
    except Exception as exc:
        return f"Error deleting skill '{safe_name}': {exc}"


async def tool_reload_skills() -> str:
    """Reload the skill registry from all discovery paths."""
    if _skill_registry is None:
        return "Error: skill registry not available"

    try:
        _skill_registry.load_all()
        skills = _skill_registry.list_skills()
        return f"Skills reloaded. {len(skills)} skill(s) now active."
    except Exception as exc:
        return f"Error reloading skills: {exc}"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_tools_section(tools_spec: str) -> str:
    """Build the ## Tools section from an optional JSON spec."""
    if not tools_spec:
        return _default_tool_section()

    try:
        specs = json.loads(tools_spec)
        if not isinstance(specs, list) or not specs:
            return _default_tool_section()

        lines = []
        for spec in specs:
            tool_name = spec.get("name", "tool")
            tool_desc = spec.get("description", "")
            lines.append(f"\n### {tool_name}")
            lines.append(tool_desc)
            params = spec.get("parameters", [])
            if params:
                lines.append("\n**Parameters:**")
                for p in params:
                    req = ", required" if p.get("required") else ""
                    lines.append(f"- `{p['name']}` ({p.get('type','string')}{req}): {p.get('description','')}")

        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        return _default_tool_section()


def _default_tool_section() -> str:
    return "\n### run\nExecute the primary action of this skill.\n\n**Parameters:**\n- `input` (string, required): The input to process."


def _extract_tool_names(tools_spec: str, fallback: str) -> list[str]:
    """Extract and sanitize tool names from a tools_spec JSON string.

    Tool names are sanitized to valid Python identifiers to prevent code
    injection when names are embedded into generated Python source files.
    """
    if tools_spec:
        try:
            specs = json.loads(tools_spec)
            raw_names = [s.get("name") for s in specs if s.get("name")]
            if raw_names:
                sanitized = [
                    re.sub(r"[^a-z0-9_]", "_", n.lower().strip()).strip("_")
                    for n in raw_names
                ]
                # Filter out empty names that became empty after sanitization
                valid = [n for n in sanitized if n]
                if valid:
                    return valid
        except (json.JSONDecodeError, TypeError):
            pass
    return [fallback]
