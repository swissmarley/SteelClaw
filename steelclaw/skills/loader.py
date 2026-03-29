"""Skill loader — discovers and loads skills from bundled, global, and workspace directories."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Optional

from steelclaw.skills.parser import SkillMetadata, ToolDefinition, parse_skill_file

logger = logging.getLogger("steelclaw.skills.loader")

# Type for a tool executor function
ToolExecutor = Callable[..., Coroutine[Any, Any, str]]


class Skill:
    """A loaded skill with its metadata and tool executors."""

    def __init__(
        self,
        metadata: SkillMetadata,
        path: Path,
        scope: str,  # "bundled" | "global" | "workspace"
        executors: dict[str, ToolExecutor] | None = None,
        default_enabled: bool = False,
    ) -> None:
        self.metadata = metadata
        self.path = path
        self.scope = scope
        self.executors: dict[str, ToolExecutor] = executors or {}
        self.default_enabled = default_enabled

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def tools(self) -> list[ToolDefinition]:
        return self.metadata.tools

    def get_openai_tools(self) -> list[dict]:
        """Return all tools in OpenAI-compatible schema."""
        return [t.to_openai_tool() for t in self.tools]

    def get_system_context(self) -> str:
        """Return skill-specific system prompt context."""
        parts = []
        if self.metadata.system_prompt:
            parts.append(self.metadata.system_prompt)
        if self.metadata.description:
            parts.append(f"Skill: {self.name} — {self.metadata.description}")
        return "\n".join(parts)

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool by name with the given arguments."""
        executor = self.executors.get(tool_name)
        if executor is None:
            return f"Error: Tool '{tool_name}' has no executor registered."
        try:
            return await executor(**arguments)
        except Exception as e:
            logger.exception("Error executing tool %s in skill %s", tool_name, self.name)
            return f"Error executing tool '{tool_name}': {e}"


def load_skill_from_directory(skill_dir: Path, scope: str) -> Skill | None:
    """Load a single skill from its directory.

    Expected structure:
        skill_dir/
        ├── SKILL.md      (required)
        ├── __init__.py   (optional — tool executor registrations)
        └── ...           (other files)
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        logger.debug("No SKILL.md in %s — skipping", skill_dir)
        return None

    metadata = parse_skill_file(skill_md)

    # Try to load Python executors from __init__.py
    init_py = skill_dir / "__init__.py"
    module = None
    executors: dict[str, ToolExecutor] = {}
    if init_py.exists():
        executors = _load_executors(init_py, skill_dir.name)
        safe_name = f"steelclaw_skill_{skill_dir.name}"
        module = sys.modules.get(safe_name)

    default_enabled = getattr(module, "default_enabled", False) if module else False
    skill = Skill(metadata=metadata, path=skill_dir, scope=scope, default_enabled=default_enabled)
    skill.executors.update(executors)

    logger.info("Loaded skill: %s (scope=%s, tools=%d)", skill.name, scope, len(skill.tools))
    return skill


def _load_executors(init_py: Path, module_name: str) -> dict[str, ToolExecutor]:
    """Dynamically load tool executor functions from a skill's __init__.py.

    The module should define a `TOOLS` dict mapping tool names to async callables:
        TOOLS = {
            "run_command": run_command,
            "search_web": search_web,
        }
    """
    executors: dict[str, ToolExecutor] = {}
    try:
        safe_name = f"steelclaw_skill_{module_name}"
        spec = importlib.util.spec_from_file_location(safe_name, init_py)
        if spec is None or spec.loader is None:
            return executors

        module = importlib.util.module_from_spec(spec)
        sys.modules[safe_name] = module
        spec.loader.exec_module(module)

        tools_map = getattr(module, "TOOLS", None)
        if isinstance(tools_map, dict):
            executors.update(tools_map)
        else:
            # Auto-discover async functions prefixed with "tool_"
            for attr_name in dir(module):
                if attr_name.startswith("tool_"):
                    fn = getattr(module, attr_name)
                    if callable(fn):
                        tool_name = attr_name[5:]  # strip "tool_" prefix
                        executors[tool_name] = fn

    except Exception:
        logger.exception("Failed to load executors from %s", init_py)

    return executors


def discover_skills(
    bundled_dir: str,
    global_dir: str,
    workspace_dir: str,
) -> list[Skill]:
    """Discover all skills from the three scoping directories.

    Priority: workspace > global > bundled (workspace overrides same-named skills).
    """
    skills_by_name: Dict[str, Skill] = {}

    # Load in priority order: bundled first, workspace last (overrides)
    for scope, dir_path in [
        ("bundled", Path(bundled_dir)),
        ("global", Path(global_dir).expanduser()),
        ("workspace", Path(workspace_dir)),
    ]:
        if not dir_path.exists():
            logger.debug("Skill directory does not exist: %s", dir_path)
            continue

        for child in sorted(dir_path.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                skill = load_skill_from_directory(child, scope)
                if skill:
                    if skill.name in skills_by_name:
                        prev = skills_by_name[skill.name]
                        logger.info(
                            "Skill '%s' from %s overrides %s version",
                            skill.name, scope, prev.scope,
                        )
                    skills_by_name[skill.name] = skill

    return list(skills_by_name.values())
