"""SKILL.md markdown parser — extracts metadata, tools, and system prompts from skill files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("steelclaw.skills.parser")


@dataclass
class ToolParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    enum: list[str] | None = None


@dataclass
class ToolDefinition:
    """A tool/function that the skill exposes to the LLM."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI-compatible tool schema for LiteLLM."""
        properties: Dict[str, Any] = {}
        required_params: List[str] = []

        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required_params.append(param.name)

        schema: Dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        }
        if required_params:
            schema["function"]["parameters"]["required"] = required_params

        return schema


@dataclass
class SkillMetadata:
    """Parsed content of a SKILL.md file."""

    name: str
    description: str = ""
    version: str = "0.1.0"
    author: str = ""
    system_prompt: str = ""
    tools: list[ToolDefinition] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # keywords that activate this skill
    raw_content: str = ""


def parse_skill_md(content: str, fallback_name: str = "unknown") -> SkillMetadata:
    """Parse a SKILL.md file into structured metadata.

    Expected format:
    ```
    # Skill Name

    Description text here.

    ## Metadata
    - version: 1.0.0
    - author: someone
    - triggers: keyword1, keyword2

    ## System Prompt
    You are a specialist in...

    ## Tools

    ### tool_name
    Description of the tool.

    **Parameters:**
    - `param_name` (string, required): Description
    - `param2` (integer): Optional param
    ```
    """
    metadata = SkillMetadata(name=fallback_name, raw_content=content)

    lines = content.strip().split("\n")
    if not lines:
        return metadata

    # Parse H1 as skill name
    if lines[0].startswith("# "):
        metadata.name = lines[0][2:].strip()

    # Split into sections by H2 headers
    sections: Dict[str, List[str]] = {}
    current_section = "description"
    section_lines: List[str] = []

    for line in lines[1:]:
        if line.startswith("## "):
            sections[current_section] = section_lines
            current_section = line[3:].strip().lower()
            section_lines = []
        else:
            section_lines.append(line)
    sections[current_section] = section_lines

    # Parse description
    if "description" in sections:
        metadata.description = "\n".join(sections["description"]).strip()

    # Parse metadata section
    if "metadata" in sections:
        for line in sections["metadata"]:
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]
            match = re.match(r"(\w+)\s*:\s*(.+)", line)
            if match:
                key, value = match.group(1).lower(), match.group(2).strip()
                if key == "version":
                    metadata.version = value
                elif key == "author":
                    metadata.author = value
                elif key == "triggers":
                    metadata.triggers = [t.strip() for t in value.split(",")]

    # Parse system prompt
    if "system prompt" in sections:
        metadata.system_prompt = "\n".join(sections["system prompt"]).strip()

    # Parse tools
    if "tools" in sections:
        metadata.tools = _parse_tools_section(sections["tools"])

    return metadata


def _parse_tools_section(lines: list[str]) -> list[ToolDefinition]:
    """Parse the ## Tools section into ToolDefinition objects."""
    tools: list[ToolDefinition] = []
    current_tool: Optional[ToolDefinition] = None
    current_desc_lines: List[str] = []
    in_parameters = False

    for line in lines:
        if line.startswith("### "):
            # Save previous tool
            if current_tool:
                if not current_tool.description:
                    current_tool.description = "\n".join(current_desc_lines).strip()
                tools.append(current_tool)

            tool_name = line[4:].strip()
            current_tool = ToolDefinition(name=tool_name, description="")
            current_desc_lines = []
            in_parameters = False

        elif current_tool is not None:
            stripped = line.strip()

            if stripped.lower().startswith("**parameters"):
                in_parameters = True
                if current_desc_lines and not current_tool.description:
                    current_tool.description = "\n".join(current_desc_lines).strip()

            elif in_parameters and stripped.startswith("- "):
                param = _parse_parameter_line(stripped[2:])
                if param:
                    current_tool.parameters.append(param)

            elif not in_parameters:
                current_desc_lines.append(line)

    # Don't forget the last tool
    if current_tool:
        if not current_tool.description:
            current_tool.description = "\n".join(current_desc_lines).strip()
        tools.append(current_tool)

    return tools


def _parse_parameter_line(line: str) -> ToolParameter | None:
    """Parse a parameter line like: `name` (string, required): Description here."""
    match = re.match(
        r"`(\w+)`\s*\(([^)]+)\)\s*:?\s*(.*)",
        line.strip(),
    )
    if not match:
        return None

    name = match.group(1)
    type_info = match.group(2)
    description = match.group(3).strip()

    parts = [p.strip().lower() for p in type_info.split(",")]
    param_type = parts[0] if parts else "string"
    required = "required" in parts

    return ToolParameter(
        name=name,
        type=param_type,
        description=description,
        required=required,
    )


def parse_skill_file(path: Path) -> SkillMetadata:
    """Read and parse a SKILL.md file from disk."""
    content = path.read_text(encoding="utf-8")
    return parse_skill_md(content, fallback_name=path.parent.name)
