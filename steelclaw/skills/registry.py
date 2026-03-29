"""Skill registry — manages loaded skills and routes tool calls to the correct skill."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from steelclaw.settings import SkillSettings
from steelclaw.skills.loader import Skill, discover_skills

logger = logging.getLogger("steelclaw.skills")


class SkillRegistry:
    """Central registry for all loaded skills."""

    def __init__(self, settings: SkillSettings) -> None:
        self._settings = settings
        self._skills: Dict[str, Skill] = {}  # active skills only
        self._all_skills: Dict[str, Skill] = {}  # all discovered skills
        self._disabled: set[str] = set(settings.disabled_skills)
        # Map tool_name → skill for fast lookup during tool call routing
        self._tool_index: Dict[str, Skill] = {}

    def load_all(self) -> None:
        """Discover and load all skills from configured directories."""
        if not self._settings.enabled:
            logger.info("Skill system disabled")
            return

        skills = discover_skills(
            bundled_dir=self._settings.bundled_dir,
            global_dir=self._settings.global_dir,
            workspace_dir=self._settings.workspace_dir,
        )

        self._skills.clear()
        self._all_skills.clear()
        self._tool_index.clear()

        for skill in skills:
            self._all_skills[skill.name] = skill
            if skill.default_enabled and skill.name in self._disabled:
                self._disabled.discard(skill.name)
                logger.info("Skill '%s' is default-enabled — overriding disabled state", skill.name)
            if skill.name in self._disabled:
                logger.info("Skill '%s' is disabled — skipping", skill.name)
                continue
            self._skills[skill.name] = skill
            for tool in skill.tools:
                if tool.name in self._tool_index:
                    prev_skill = self._tool_index[tool.name]
                    logger.warning(
                        "Tool name collision: '%s' in skill '%s' overrides '%s'",
                        tool.name, skill.name, prev_skill.name,
                    )
                self._tool_index[tool.name] = skill

        logger.info(
            "Skill registry loaded: %d active / %d total skills, %d tools",
            len(self._skills), len(self._all_skills), len(self._tool_index),
        )

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_skill_for_tool(self, tool_name: str) -> Skill | None:
        return self._tool_index.get(tool_name)

    def get_all_tools_schema(self) -> list[dict]:
        """Return all tool schemas across all skills in OpenAI format."""
        tools = []
        for skill in self._skills.values():
            tools.extend(skill.get_openai_tools())
        return tools

    def get_combined_system_context(self) -> str:
        """Return combined system context from all loaded skills."""
        contexts = []
        for skill in self._skills.values():
            ctx = skill.get_system_context()
            if ctx:
                contexts.append(ctx)
        return "\n\n---\n\n".join(contexts) if contexts else ""

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call, routing to the correct skill."""
        skill = self._tool_index.get(tool_name)
        if skill is None:
            return f"Error: Unknown tool '{tool_name}'. Available: {list(self._tool_index.keys())}"
        return await skill.execute_tool(tool_name, arguments)

    @property
    def skills(self) -> Dict[str, Skill]:
        return dict(self._skills)

    @property
    def all_skills(self) -> Dict[str, Skill]:
        """All discovered skills including disabled ones."""
        return dict(self._all_skills)

    @property
    def disabled_skills(self) -> list[str]:
        return list(self._disabled)

    def enable_skill(self, name: str) -> bool:
        """Enable a disabled skill at runtime."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        self._disabled.discard(name)
        if name not in self._skills:
            self._skills[name] = skill
            for tool in skill.tools:
                self._tool_index[tool.name] = skill
        logger.info("Skill '%s' enabled", name)
        return True

    def disable_skill(self, name: str) -> bool:
        """Disable a skill at runtime."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        if skill.default_enabled:
            logger.warning("Cannot disable default-enabled skill '%s'", name)
            return False
        self._disabled.add(name)
        self._skills.pop(name, None)
        for tool in skill.tools:
            if self._tool_index.get(tool.name) is skill:
                del self._tool_index[tool.name]
        logger.info("Skill '%s' disabled", name)
        return True

    def get_skill_credentials(self, name: str) -> list[dict] | None:
        """Return the skill's required_credentials with current values masked."""
        skill = self._all_skills.get(name)
        if skill is None:
            return None
        stored = self._settings.skill_configs.get(name, {})
        result = []
        for cred in skill.required_credentials:
            value = stored.get(cred["key"], "")
            masked = ""
            if value:
                masked = "****" + value[-4:] if len(value) > 4 else "****"
            result.append({
                "key": cred["key"],
                "label": cred.get("label", cred["key"]),
                "type": cred.get("type", "password"),
                "test_url": cred.get("test_url"),
                "value": masked,
                "is_set": bool(value),
            })
        return result

    def set_skill_credentials(self, name: str, credentials: dict[str, str]) -> bool:
        """Save credentials for a skill into skill_configs."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        if name not in self._settings.skill_configs:
            self._settings.skill_configs[name] = {}
        for key, value in credentials.items():
            if value and not value.startswith("****"):
                self._settings.skill_configs[name][key] = value
        return True

    def find_skills_by_trigger(self, content: str) -> list[Skill]:
        """Find skills whose triggers match the given content."""
        content_lower = content.lower()
        matched = []
        for skill in self._skills.values():
            for trigger in skill.metadata.triggers:
                if trigger.lower() in content_lower:
                    matched.append(skill)
                    break
        return matched
