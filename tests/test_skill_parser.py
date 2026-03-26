"""Tests for the SKILL.md parser."""

from __future__ import annotations

from steelclaw.skills.parser import parse_skill_md


SAMPLE_SKILL_MD = """\
# Web Search

Search the web for information.

## Metadata
- version: 2.1.0
- author: SteelClaw Team
- triggers: search, google, find

## System Prompt
You can search the web using the search_web tool.
Always cite your sources.

## Tools

### search_web
Search the web and return relevant results.

**Parameters:**
- `query` (string, required): The search query
- `max_results` (integer): Maximum number of results to return
- `language` (string): Language code (e.g., en, de, fr)

### fetch_page
Fetch the content of a specific URL.

**Parameters:**
- `url` (string, required): The URL to fetch
"""


def test_parse_name():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    assert meta.name == "Web Search"


def test_parse_description():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    assert "Search the web" in meta.description


def test_parse_metadata():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    assert meta.version == "2.1.0"
    assert meta.author == "SteelClaw Team"
    assert meta.triggers == ["search", "google", "find"]


def test_parse_system_prompt():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    assert "search the web" in meta.system_prompt.lower()
    assert "cite your sources" in meta.system_prompt.lower()


def test_parse_tools():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    assert len(meta.tools) == 2
    assert meta.tools[0].name == "search_web"
    assert meta.tools[1].name == "fetch_page"


def test_parse_tool_parameters():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    tool = meta.tools[0]  # search_web
    assert len(tool.parameters) == 3

    query_param = tool.parameters[0]
    assert query_param.name == "query"
    assert query_param.type == "string"
    assert query_param.required is True

    max_param = tool.parameters[1]
    assert max_param.name == "max_results"
    assert max_param.type == "integer"
    assert max_param.required is False


def test_to_openai_tool():
    meta = parse_skill_md(SAMPLE_SKILL_MD)
    tool_schema = meta.tools[0].to_openai_tool()

    assert tool_schema["type"] == "function"
    assert tool_schema["function"]["name"] == "search_web"
    assert "query" in tool_schema["function"]["parameters"]["properties"]
    assert "query" in tool_schema["function"]["parameters"]["required"]


def test_fallback_name():
    meta = parse_skill_md("No header here", fallback_name="my_skill")
    assert meta.name == "my_skill"


def test_empty_content():
    meta = parse_skill_md("")
    assert meta.name == "unknown"
    assert meta.tools == []
