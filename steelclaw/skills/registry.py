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
        self._explicitly_enabled: set[str] = set(settings.enabled_skills)
        # Map tool_name → skill for fast lookup during tool call routing
        self._tool_index: Dict[str, Skill] = {}

    def load_all(self) -> None:
        """Discover and load all skills from configured directories.

        Default behaviour:
        - Skills WITHOUT required_credentials → enabled by default
        - Skills WITH required_credentials → disabled by default (user must enable)
        - Skills the user explicitly enabled/disabled override the defaults
        """
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

            # Determine if skill should be active
            if skill.name in self._disabled:
                if not skill.default_enabled:
                    logger.info("Skill '%s' is explicitly disabled — skipping", skill.name)
                    continue
                # default_enabled skills cannot be disabled — silently restore them
                logger.info("Skill '%s' is default_enabled and cannot be disabled", skill.name)
                self._disabled.discard(skill.name)

            if skill.name in self._explicitly_enabled:
                # User explicitly enabled this skill
                pass
            elif skill.required_credentials and not skill.default_enabled:
                # Skills needing API keys are disabled by default
                logger.info(
                    "Skill '%s' requires credentials — disabled by default (enable in Skills page)",
                    skill.name,
                )
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

    def _is_skill_configured(self, skill: "Skill") -> bool:
        """Check if a skill's required credentials are all set."""
        if not skill.required_credentials:
            return True  # no credentials needed
        stored = self._settings.skill_configs.get(skill.name, {})
        for cred in skill.required_credentials:
            if not stored.get(cred["key"]):
                return False
        return True

    def get_all_tools_schema(self) -> list[dict]:
        """Return tool schemas only from skills whose credentials are configured."""
        tools = []
        for skill in self._skills.values():
            if self._is_skill_configured(skill):
                tools.extend(skill.get_openai_tools())
        return tools

    def get_combined_system_context(self) -> str:
        """Return combined system context from configured skills only."""
        contexts = []
        for skill in self._skills.values():
            if self._is_skill_configured(skill):
                ctx = skill.get_system_context()
                if ctx:
                    contexts.append(ctx)
        return "\n\n---\n\n".join(contexts) if contexts else ""

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call, routing to the correct skill."""
        skill = self._tool_index.get(tool_name)
        if skill is None:
            return f"Error: Unknown tool '{tool_name}'. Available: {list(self._tool_index.keys())}"
        if not self._is_skill_configured(skill):
            return (
                f"Error: Skill '{skill.name}' requires API credentials that are not configured. "
                f"Use web_search instead, or configure credentials in Settings > Skills."
            )
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
        self._explicitly_enabled.add(name)
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
        self._disabled.add(name)
        self._explicitly_enabled.discard(name)
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
