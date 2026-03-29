"""Tests for the SkillRegistry."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from steelclaw.skills.loader import Skill
from steelclaw.skills.parser import SkillMetadata, ToolDefinition, ToolParameter
from steelclaw.skills.registry import SkillRegistry


def _make_skill(
    name: str,
    tools: list[ToolDefinition] | None = None,
    triggers: list[str] | None = None,
) -> Skill:
    """Helper to create a minimal Skill object for testing."""
    meta = SkillMetadata(
        name=name,
        description=f"Test skill {name}",
        tools=tools or [],
        triggers=triggers or [],
        system_prompt="",
        version="1.0",
        author="test",
    )
    return Skill(metadata=meta, path=Path(f"/fake/{name}"), scope="bundled")


def _make_tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Tool {name}",
        parameters=[],
    )


def _make_settings(**overrides):
    defaults = {
        "enabled": True,
        "bundled_dir": "/nonexistent/bundled",
        "global_dir": "/nonexistent/global",
        "workspace_dir": "/nonexistent/workspace",
        "disabled_skills": [],
    }
    defaults.update(overrides)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


class TestSkillRegistryManual:
    """Tests that inject skills directly without hitting the filesystem."""

    def test_get_skill_found(self):
        reg = SkillRegistry(_make_settings())
        skill = _make_skill("notes")
        reg._skills["notes"] = skill
        assert reg.get_skill("notes") is skill

    def test_get_skill_not_found(self):
        reg = SkillRegistry(_make_settings())
        assert reg.get_skill("nonexistent") is None

    def test_get_skill_for_tool(self):
        reg = SkillRegistry(_make_settings())
        tool = _make_tool("save_note")
        skill = _make_skill("notes", tools=[tool])
        reg._skills["notes"] = skill
        reg._tool_index["save_note"] = skill
        assert reg.get_skill_for_tool("save_note") is skill

    def test_get_skill_for_tool_not_found(self):
        reg = SkillRegistry(_make_settings())
        assert reg.get_skill_for_tool("unknown_tool") is None

    def test_skills_property_returns_copy(self):
        reg = SkillRegistry(_make_settings())
        skill = _make_skill("calc")
        reg._skills["calc"] = skill
        copy = reg.skills
        copy["injected"] = _make_skill("injected")
        assert "injected" not in reg._skills

    def test_get_all_tools_schema(self):
        reg = SkillRegistry(_make_settings())
        tool = _make_tool("run_calc")
        skill = _make_skill("calc", tools=[tool])
        reg._skills["calc"] = skill
        schemas = reg.get_all_tools_schema()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "run_calc"

    def test_get_combined_system_context_empty(self):
        reg = SkillRegistry(_make_settings())
        assert reg.get_combined_system_context() == ""

    def test_find_skills_by_trigger(self):
        reg = SkillRegistry(_make_settings())
        skill = _make_skill("weather", triggers=["weather", "forecast"])
        reg._skills["weather"] = skill
        matched = reg.find_skills_by_trigger("What's the weather today?")
        assert skill in matched

    def test_find_skills_by_trigger_no_match(self):
        reg = SkillRegistry(_make_settings())
        skill = _make_skill("weather", triggers=["weather"])
        reg._skills["weather"] = skill
        assert reg.find_skills_by_trigger("Tell me a joke") == []

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self):
        reg = SkillRegistry(_make_settings())
        result = await reg.execute_tool("no_such_tool", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        reg = SkillRegistry(_make_settings())

        async def fake_executor(**kwargs):
            return "ok"

        tool = _make_tool("my_tool")
        skill = _make_skill("test_skill", tools=[tool])
        skill.executors["my_tool"] = fake_executor
        reg._skills["test_skill"] = skill
        reg._tool_index["my_tool"] = skill
        result = await reg.execute_tool("my_tool", {})
        assert result == "ok"


class TestSkillRegistryLoadAll:
    """Tests for load_all with filesystem skills."""

    def test_load_all_disabled(self):
        reg = SkillRegistry(_make_settings(enabled=False))
        reg.load_all()
        assert len(reg._skills) == 0

    def test_load_all_with_disabled_skills(self, tmp_path):
        """Skills listed in disabled_skills should be excluded."""
        # Create two minimal skill dirs
        for name in ["alpha", "beta"]:
            skill_dir = tmp_path / name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test\ntools: []\n---\n"
            )

        settings = _make_settings(
            bundled_dir=str(tmp_path),
            disabled_skills=["beta"],
        )
        reg = SkillRegistry(settings)
        reg.load_all()
        assert "alpha" in reg._skills
        assert "beta" not in reg._skills


class TestDefaultEnabledFlag:
    """Tests for the default_enabled skill behavior."""

    def test_default_enabled_skill_not_disabled(self):
        from unittest.mock import patch

        settings = _make_settings(disabled_skills=["web_search"])
        registry = SkillRegistry(settings)
        mock_web = MagicMock()
        mock_web.name = "web_search"
        mock_web.default_enabled = True
        mock_web.tools = []
        mock_web.metadata = MagicMock()
        mock_web.metadata.triggers = []

        mock_other = MagicMock()
        mock_other.name = "other_skill"
        mock_other.default_enabled = False
        mock_other.tools = []
        mock_other.metadata = MagicMock()
        mock_other.metadata.triggers = []

        with patch("steelclaw.skills.registry.discover_skills", return_value=[mock_web, mock_other]):
            registry.load_all()
        assert registry.get_skill("web_search") is not None
        assert "web_search" not in registry.disabled_skills

    def test_non_default_skill_stays_disabled(self):
        from unittest.mock import patch

        settings = _make_settings(disabled_skills=["other_skill"])
        registry = SkillRegistry(settings)
        mock_other = MagicMock()
        mock_other.name = "other_skill"
        mock_other.default_enabled = False
        mock_other.tools = []
        mock_other.metadata = MagicMock()
        mock_other.metadata.triggers = []

        with patch("steelclaw.skills.registry.discover_skills", return_value=[mock_other]):
            registry.load_all()
        assert registry.get_skill("other_skill") is None
        assert "other_skill" in registry.disabled_skills
