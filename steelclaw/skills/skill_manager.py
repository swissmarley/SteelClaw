"""Skill manager — manages Claude-compatible skills (instruction bundles).

Unlike the ToolRegistry which manages tools (bundled integrations with Python
executors), the SkillManager handles *skills* — self-contained SKILL.md
manifests that provide instructions and context to the agent without
executable tool functions.

Skills are stored in configurable directories:
  - global_dir:   ~/.steelclaw/claude-skills  (user-installed skills)
  - workspace_dir: .claude-skills              (project-specific skills)

Each skill is a folder containing at least a SKILL.md file. Skills are
100% compatible with Claude Skills format — exported skills import directly
into Claude, and Claude skills import directly into SteelClaw.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from steelclaw.skills.loader import Skill, load_skill_from_directory
from steelclaw.skills.parser import SkillMetadata, parse_skill_file, parse_skill_md

logger = logging.getLogger("steelclaw.skills.manager")


class SkillManager:
    """Manages the lifecycle of Claude-compatible skills.

    Handles discovery, CRUD, import/export, enable/disable, and trigger-based
    matching for skills (instruction-only bundles, not tools with executors).
    """

    def __init__(
        self,
        global_dir: str = "~/.steelclaw/claude-skills",
        workspace_dir: str = ".claude-skills",
        enabled: bool = True,
        disabled_skills: list[str] | None = None,
        enabled_skills: list[str] | None = None,
    ) -> None:
        self._global_dir = Path(global_dir).expanduser().resolve()
        self._workspace_dir = Path(workspace_dir).resolve()
        self._enabled = enabled
        self._disabled: set[str] = set(disabled_skills or [])
        self._explicitly_enabled: set[str] = set(enabled_skills or [])
        self._skills: Dict[str, Skill] = {}  # active skills
        self._all_skills: Dict[str, Skill] = {}  # all discovered (including disabled)

    @property
    def global_dir(self) -> Path:
        return self._global_dir

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    def load_all(self) -> None:
        """Discover and load all skills from configured directories."""
        if not self._enabled:
            logger.info("Skill system disabled")
            return

        self._skills.clear()
        self._all_skills.clear()

        skills_by_name: Dict[str, Skill] = {}

        # Load in priority order: global first, workspace overrides
        for scope, dir_path in [
            ("global", self._global_dir),
            ("workspace", self._workspace_dir),
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

        # Determine enabled/disabled state
        for name, skill in skills_by_name.items():
            self._all_skills[name] = skill
            if name in self._disabled:
                logger.debug("Skill '%s' is disabled — skipping", name)
                continue
            if name in self._explicitly_enabled or not skill.required_credentials:
                self._skills[name] = skill

        logger.info(
            "Skill manager loaded: %d active / %d total skills",
            len(self._skills), len(self._all_skills),
        )

    def get_skill(self, name: str) -> Skill | None:
        """Get an active skill by name."""
        return self._skills.get(name)

    def get_all_skill(self, name: str) -> Skill | None:
        """Get any skill by name (including disabled)."""
        return self._all_skills.get(name)

    @property
    def skills(self) -> Dict[str, Skill]:
        """Active skills (enabled and configured)."""
        return dict(self._skills)

    @property
    def all_skills(self) -> Dict[str, Skill]:
        """All discovered skills including disabled."""
        return dict(self._all_skills)

    @property
    def disabled_skills(self) -> list[str]:
        return list(self._disabled)

    def enable_skill(self, name: str) -> bool:
        """Enable a skill at runtime."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        self._disabled.discard(name)
        self._explicitly_enabled.add(name)
        if name not in self._skills:
            self._skills[name] = skill
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
        logger.info("Skill '%s' disabled", name)
        return True

    def find_skills_by_trigger(self, content: str) -> list[Skill]:
        """Find active skills whose triggers match the given content."""
        content_lower = content.lower()
        matched = []
        for skill in self._skills.values():
            for trigger in skill.metadata.triggers:
                if trigger.lower() in content_lower:
                    matched.append(skill)
                    break
        return matched

    def get_combined_system_context(self) -> str:
        """Return combined system context from all active skills."""
        contexts = []
        for skill in self._skills.values():
            ctx = skill.get_system_context()
            if ctx:
                contexts.append(ctx)
        return "\n\n---\n\n".join(contexts) if contexts else ""

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create_skill(
        self,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "",
        triggers: list[str] | None = None,
        system_prompt: str = "",
        scope: str = "global",
    ) -> Skill:
        """Create a new skill from parameters and save to disk.

        Args:
            name: Skill name (will be sanitized for directory name).
            description: Short description of the skill.
            version: Semantic version.
            author: Author name.
            triggers: List of trigger keywords.
            system_prompt: The skill's instruction content.
            scope: 'global' or 'workspace'.

        Returns:
            The newly created Skill object.
        """
        safe_name = self._sanitize_name(name)
        skill_dir = self._dir_for_scope(safe_name, scope)
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Build SKILL.md content
        trigger_line = ", ".join(triggers) if triggers else ""
        parts = [
            f"# {name}",
            "",
            description,
            "",
            "## Metadata",
            f"- version: {version}",
            f"- author: {author}",
        ]
        if trigger_line:
            parts.append(f"- triggers: {trigger_line}")
        if system_prompt:
            parts.extend(["", "## System Prompt", "", system_prompt])

        skill_md = "\n".join(parts)
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        # Reload and return
        self.load_all()
        skill = self._all_skills.get(safe_name)
        if skill is None:
            raise ValueError(f"Failed to load newly created skill '{safe_name}'")
        return skill

    def delete_skill(self, name: str) -> bool:
        """Delete a skill and its directory from disk."""
        skill = self._all_skills.get(name)
        if skill is None:
            return False
        # Remove directory
        if skill.path.exists():
            shutil.rmtree(skill.path)
        # Remove from registries
        self._skills.pop(name, None)
        self._all_skills.pop(name, None)
        self._disabled.discard(name)
        self._explicitly_enabled.discard(name)
        logger.info("Skill '%s' deleted", name)
        return True

    def import_skill(self, source: Path, scope: str = "global") -> Skill:
        """Import a skill from a file path (.md or .zip), directory, or URL.

        Args:
            source: Path to SKILL.md file, .zip file, or skill directory.
            scope: 'global' or 'workspace'.

        Returns:
            The imported Skill object.
        """
        source = Path(source).resolve()

        if source.is_file() and source.suffix == ".md":
            return self._import_skill_md(source, scope)
        elif source.is_file() and source.suffix == ".zip":
            return self._import_skill_zip(source, scope)
        elif source.is_dir():
            return self._import_skill_dir(source, scope)
        else:
            raise ValueError(f"Unsupported source: {source}. Expected .md, .zip, or directory.")

    def _import_skill_md(self, md_path: Path, scope: str) -> Skill:
        """Import a skill from a standalone SKILL.md file."""
        metadata = parse_skill_file(md_path)
        safe_name = self._sanitize_name(metadata.name)
        dest_dir = self._dir_for_scope(safe_name, scope)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md_path, dest_dir / "SKILL.md")

        self.load_all()
        skill = self._all_skills.get(safe_name)
        if skill is None:
            raise ValueError(f"Failed to load imported skill '{safe_name}'")
        return skill

    def _import_skill_zip(self, zip_path: Path, scope: str) -> Skill:
        """Import a skill from a zip archive containing SKILL.md."""
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)

            # Find SKILL.md in the extracted content
            tmp_path = Path(tmp)
            skill_md = None
            for candidate in tmp_path.rglob("SKILL.md"):
                skill_md = candidate
                break

            if skill_md is None:
                raise ValueError(f"No SKILL.md found in {zip_path}")

            # Determine the skill directory (parent of SKILL.md)
            skill_dir = skill_md.parent
            metadata = parse_skill_file(skill_md)
            safe_name = self._sanitize_name(metadata.name)
            dest_dir = self._dir_for_scope(safe_name, scope)
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Copy entire skill directory
            shutil.copytree(skill_dir, dest_dir, dirs_exist_ok=True)

            self.load_all()
            skill = self._all_skills.get(safe_name)
            if skill is None:
                raise ValueError(f"Failed to load imported skill '{safe_name}'")
            return skill

    def _import_skill_dir(self, source_dir: Path, scope: str) -> Skill:
        """Import a skill from an existing directory containing SKILL.md."""
        skill_md = source_dir / "SKILL.md"
        if not skill_md.exists():
            raise ValueError(f"No SKILL.md found in {source_dir}")

        metadata = parse_skill_file(skill_md)
        safe_name = self._sanitize_name(metadata.name)
        dest_dir = self._dir_for_scope(safe_name, scope)
        dest_dir.mkdir(parents=True, exist_ok=True)

        shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)

        self.load_all()
        skill = self._all_skills.get(safe_name)
        if skill is None:
            raise ValueError(f"Failed to load imported skill '{safe_name}'")
        return skill

    def export_skill(self, name: str, output_path: Path | None = None) -> Path:
        """Export a skill as a zip archive compatible with Claude Skills format.

        Args:
            name: Skill name to export.
            output_path: Optional output path. Defaults to <name>.zip in temp dir.

        Returns:
            Path to the created zip file.
        """
        skill = self._all_skills.get(name)
        if skill is None:
            raise ValueError(f"Skill '{name}' not found")

        if output_path is None:
            output_path = Path(tempfile.mkdtemp()) / f"{name}.zip"

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in skill.path.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    arcname = f"{skill.path.name}/{file_path.relative_to(skill.path)}"
                    zf.write(file_path, arcname)

        logger.info("Skill '%s' exported to %s", name, output_path)
        return output_path

    def generate_skill(self, description: str, llm_provider=None) -> Skill:
        """Generate a new skill from a natural language description using AI.

        Args:
            description: Natural language description of what the skill should do.
            llm_provider: Optional LLM provider. If None, uses built-in generation.

        Returns:
            The generated Skill object.
        """
        import re

        # Sanitize the description into a skill name
        safe_name = self._sanitize_name(
            re.sub(r"[^a-z0-9\s]", "", description.lower())[:30]
        )
        if not safe_name or safe_name == "auto_skill":
            safe_name = f"skill_{len(self._all_skills) + 1}"

        # Generate triggers from description keywords
        words = re.findall(r"\b\w{4,}\b", description.lower())
        triggers = list(set(words))[:5]

        # Generate system prompt
        system_prompt = (
            f"You are a specialist in {description.lower()}. "
            f"Apply your expertise to help the user with tasks related to this domain. "
            f"Be thorough, accurate, and provide actionable guidance."
        )

        if llm_provider is not None:
            # Use LLM to generate a richer skill
            return self._generate_with_llm(description, safe_name, llm_provider)

        # Fallback: create skill from description
        return self.create_skill(
            name=safe_name,
            description=description[:200],
            triggers=triggers,
            system_prompt=system_prompt,
            scope="global",
        )

    async def generate_skill_async(self, description: str, llm_provider) -> Skill:
        """Async version of generate_skill that uses the LLM for richer output."""
        import json
        import re

        from steelclaw.skills.generator import _parse_json_response, _sanitize_name as _gen_sanitize

        prompt = f"""You are a skill definition generator. Create a Claude-compatible skill based on this description:

Description: {description}

Respond with ONLY a JSON object:
{{
  "name": "snake_case_skill_name",
  "description": "One-sentence description",
  "version": "1.0.0",
  "author": "SteelClaw",
  "triggers": ["keyword1", "keyword2", "keyword3"],
  "system_prompt": "Detailed instruction content for the skill..."
}}"""

        try:
            response = await llm_provider.complete(
                messages=[
                    {"role": "system", "content": "You are a skill definition generator."},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
            )
            raw = (response.content or "").strip()
            parsed = _parse_json_response(raw)

            if parsed and parsed.get("name"):
                return self.create_skill(
                    name=parsed["name"],
                    description=parsed.get("description", description),
                    version=parsed.get("version", "1.0.0"),
                    author=parsed.get("author", "SteelClaw"),
                    triggers=parsed.get("triggers", []),
                    system_prompt=parsed.get("system_prompt", ""),
                    scope="global",
                )
        except Exception as exc:
            logger.warning("LLM skill generation failed: %s", exc)

        # Fallback to template-based generation
        return self.generate_skill(description)

    def _generate_with_llm(self, description: str, name: str, llm_provider) -> Skill:
        """Synchronous wrapper — use generate_skill_async instead."""
        raise NotImplementedError("Use generate_skill_async for LLM-based generation")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sanitize_name(self, name: str) -> str:
        """Convert a skill name to a safe directory name."""
        import re
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9_]", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        return name or "skill"

    def _dir_for_scope(self, name: str, scope: str) -> Path:
        """Get the directory path for a skill name in the given scope."""
        if scope == "workspace":
            return self._workspace_dir / name
        return self._global_dir / name