"""Autonomous skill generator — reflects on recent tool calls and creates reusable skills.

After the agent completes a task that required N+ tool calls (configurable via
``reflection.threshold``), the SkillGenerator analyses the tool-call pattern and:

1. Decides whether a reusable skill would be valuable.
2. Generates a SKILL.md + __init__.py using the LLM.
3. Validates the generated SKILL.md can be parsed without errors.
4. If ``skill_auto_create=True``, writes the files to ``~/.steelclaw/skills/<name>/``
   and triggers a hot-reload of the skill registry.

When ``skill_auto_create=False`` (the safe default), the reflection is only
*logged* — no files are written, but the reasoning is preserved in the database
for manual review.
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from steelclaw.llm.provider import LLMProvider
    from steelclaw.skills.registry import SkillRegistry

logger = logging.getLogger("steelclaw.skills.generator")

# Prompt asking the LLM to decide whether a skill is worth creating
_REFLECT_PROMPT = textwrap.dedent("""\
    You are a meta-agent reviewing your own recent tool-call history to identify
    patterns that could be packaged into a reusable skill.

    ## Recent tool calls
    {tool_calls_summary}

    ## Task context
    {task_context}

    ## Instructions
    1. Analyse the tool calls for a repeated or composable pattern.
    2. If a valuable reusable skill can be distilled, reply with a JSON object:
       {{
         "should_create": true,
         "skill_name": "snake_case_name",   // e.g. "git_helper"
         "description": "One-sentence description",
         "skill_md": "<full SKILL.md content>",
         "init_py": "<full __init__.py content with async tool_ functions>"
       }}
    3. If no skill is warranted, reply with:
       {{
         "should_create": false,
         "reason": "Brief explanation"
       }}

    Respond with ONLY the JSON — no additional text.
""")

# Minimal SKILL.md template used as a fallback if LLM output is malformed
_SKILL_MD_TEMPLATE = """\
# {skill_name}

{description}

## Metadata
- version: 0.1.0
- author: SteelClaw AutoGen

## System Prompt
You are a specialist in {description_lower}. Use the provided tools to help the user.

## Tools

### {tool_name}
Perform the core operation of this skill.

**Parameters:**
- `input` (string, required): The input to process.
"""

# Minimal __init__.py template
_INIT_PY_TEMPLATE = '''\
"""Auto-generated skill: {skill_name}."""

from __future__ import annotations


async def tool_{tool_name}(input: str) -> str:
    """Perform the core operation of this skill."""
    # TODO: implement this skill
    return f"Skill {skill_name!r} received: {{input}}"
'''


class SkillGenerator:
    """Reflects on tool-call history and optionally creates new skills."""

    def __init__(
        self,
        llm_provider: "LLMProvider",
        global_skills_dir: Path,
        skill_registry: "SkillRegistry | None" = None,
    ) -> None:
        self._provider = llm_provider
        self._global_dir = Path(global_skills_dir).expanduser().resolve()
        self._registry = skill_registry

    def set_registry(self, registry: "SkillRegistry") -> None:
        """Inject the skill registry for hot-reload after skill creation."""
        self._registry = registry

    async def reflect_and_create(
        self,
        tool_calls_log: list[dict[str, Any]],
        task_context: str,
        skill_auto_create: bool = False,
    ) -> dict[str, Any]:
        """Analyse tool-call history and optionally generate a new skill.

        Args:
            tool_calls_log: List of dicts with keys ``name`` and ``arguments``.
            task_context: Short description of the overall task.
            skill_auto_create: If True, write generated files to disk.

        Returns:
            A result dict with keys:
            - ``reflected``: bool
            - ``should_create``: bool
            - ``skill_name``: str or None
            - ``skill_path``: str or None
            - ``reason``: str (explanation)
        """
        result: dict[str, Any] = {
            "reflected": True,
            "should_create": False,
            "skill_name": None,
            "skill_path": None,
            "reason": "",
        }

        if not tool_calls_log:
            result["reflected"] = False
            result["reason"] = "No tool calls to reflect on"
            return result

        # Summarise the tool calls for the prompt
        tool_calls_summary = _summarise_tool_calls(tool_calls_log)

        prompt_text = _REFLECT_PROMPT.format(
            tool_calls_summary=tool_calls_summary,
            task_context=task_context or "General task",
        )

        try:
            response = await self._provider.complete(
                messages=[
                    {"role": "system", "content": "You are a meta-reasoning agent."},
                    {"role": "user", "content": prompt_text},
                ],
                tools=None,
            )
        except Exception as exc:
            logger.warning("Reflection LLM call failed: %s", exc)
            result["reason"] = f"LLM call failed: {exc}"
            return result

        raw = (response.content or "").strip()
        parsed = _parse_json_response(raw)

        if parsed is None:
            logger.warning("Reflection response was not valid JSON: %s", raw[:200])
            result["reason"] = "Could not parse LLM reflection response"
            return result

        if not parsed.get("should_create"):
            result["reason"] = parsed.get("reason", "LLM decided no skill needed")
            logger.info("Reflection: no skill created — %s", result["reason"])
            return result

        # LLM wants to create a skill
        skill_name = _sanitise_name(parsed.get("skill_name", "auto_skill"))
        description = parsed.get("description", "Auto-generated skill")
        skill_md = parsed.get("skill_md") or _SKILL_MD_TEMPLATE.format(
            skill_name=skill_name.replace("_", " ").title(),
            description=description,
            description_lower=description.lower(),
            tool_name=skill_name,
        )
        init_py = parsed.get("init_py") or _INIT_PY_TEMPLATE.format(
            skill_name=skill_name,
            tool_name=skill_name,
        )

        # Validate SKILL.md before writing
        if not _validate_skill_md(skill_md, skill_name):
            result["reason"] = "Generated SKILL.md failed validation"
            return result

        result["should_create"] = True
        result["skill_name"] = skill_name

        if not skill_auto_create:
            result["reason"] = (
                f"Skill '{skill_name}' identified but auto-create is disabled. "
                "Enable agents.reflection.skill_auto_create to write it to disk."
            )
            logger.info("Reflection: would create skill '%s' (auto-create disabled)", skill_name)
            return result

        # Write files to ~/.steelclaw/skills/<skill_name>/
        try:
            skill_path = self._save_skill(skill_name, skill_md, init_py)
            result["skill_path"] = str(skill_path)
            result["reason"] = f"Skill '{skill_name}' created at {skill_path}"
            logger.info("Autonomous skill created: %s", skill_path)

            # Hot-reload the registry
            if self._registry is not None:
                self._registry.load_all()
                logger.info("Skill registry reloaded after autonomous creation")
        except Exception as exc:
            logger.error("Failed to write skill '%s': %s", skill_name, exc)
            result["should_create"] = False
            result["reason"] = f"Failed to write skill files: {exc}"

        return result

    def _save_skill(self, name: str, skill_md: str, init_py: str) -> Path:
        """Write skill files to ~/.steelclaw/skills/<name>/."""
        skill_dir = self._global_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (skill_dir / "__init__.py").write_text(init_py, encoding="utf-8")

        return skill_dir


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_json_by_braces(text: str) -> dict | None:
    """Extract a JSON object from text using balanced brace counting.

    This handles nested objects correctly, unlike regex greedy/non-greedy matching.
    """
    start = None
    depth = 0

    for i, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    continue

    return None

def _summarise_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """Format tool calls into a compact human-readable summary."""
    lines = []
    for i, tc in enumerate(tool_calls, 1):
        name = tc.get("name", "unknown")
        args = tc.get("arguments", {})
        args_str = json.dumps(args, ensure_ascii=False)[:120]
        lines.append(f"{i}. {name}({args_str})")
    return "\n".join(lines)


def _parse_json_response(text: str) -> dict | None:
    """Extract and parse a JSON object from the LLM response."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block from markdown code fences
    # Find the first opening brace and use balanced brace counting
    code_block_match = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if code_block_match:
        block_content = code_block_match.group(1)
        json_obj = _extract_json_by_braces(block_content)
        if json_obj:
            return json_obj

    # Try finding raw JSON object in text using balanced brace counting
    json_obj = _extract_json_by_braces(text)
    if json_obj:
        return json_obj

    return None


def _sanitise_name(name: str) -> str:
    """Convert a skill name to a safe snake_case directory name."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "auto_skill"


def _validate_skill_md(skill_md: str, skill_name: str) -> bool:
    """Return True if the SKILL.md can be parsed without errors."""
    try:
        from steelclaw.skills.parser import parse_skill_md
        metadata = parse_skill_md(skill_md, fallback_name=skill_name)
        return bool(metadata.name)
    except Exception as exc:
        logger.warning("SKILL.md validation failed for '%s': %s", skill_name, exc)
        return False
