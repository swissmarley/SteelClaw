"""Tests for the streaming agent tool-calling loop — verifies tool results
are properly fed back and the loop exits when the LLM returns text."""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from steelclaw.agents.router import AgentRouter
from steelclaw.llm.context import ContextBuilder
from steelclaw.llm.provider import LLMProvider, StreamChunk, ToolCall
from steelclaw.schemas.messages import InboundMessage
from steelclaw.settings import AgentSettings


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_inbound(text: str = "list n8n workflows") -> InboundMessage:
    return InboundMessage(
        platform="websocket",
        platform_chat_id="test-chat",
        platform_user_id="test-user",
        content=text,
    )


def _make_session():
    session = MagicMock()
    session.id = "sess-1"
    session.unified_session_id = None
    return session


def _text_chunk(text: str) -> StreamChunk:
    chunk = StreamChunk(content=text, finish_reason="stop")
    return chunk


def _tool_chunk(name: str, call_id: str, arguments: str = "{}") -> list[StreamChunk]:
    """Produce the two-chunk sequence that represents a streaming tool call."""
    first = StreamChunk(
        tool_call_delta={"index": 0, "id": call_id, "name": name, "arguments": ""},
        finish_reason=None,
    )
    last = StreamChunk(
        tool_call_delta={"index": 0, "id": None, "name": None, "arguments": arguments},
        finish_reason="tool_calls",
    )
    return [first, last]


async def _make_stream(*chunks: StreamChunk) -> AsyncIterator[StreamChunk]:
    for chunk in chunks:
        yield chunk


# ── tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_tool_loop_exits_after_one_round():
    """After one tool call + result, the second LLM call returns text → loop exits."""
    settings = AgentSettings()
    router = AgentRouter(settings)

    # Round 1: LLM returns a tool call
    # Round 2: LLM returns plain text
    call_count = 0

    async def fake_stream(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            for chunk in _tool_chunk("list_workflows", "call_abc"):
                yield chunk
        else:
            yield _text_chunk("Here are your workflows: none found.")

    router._provider = MagicMock()
    router._provider.stream = fake_stream

    # Mock context builder — no DB needed
    router._context = MagicMock()
    router._context.build = AsyncMock(return_value=[
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "list n8n workflows"},
    ])
    router._context._build_user_message = lambda text, att=None: {"role": "user", "content": text}
    router._context.build_assistant_tool_call_message = ContextBuilder(settings.llm).build_assistant_tool_call_message
    router._context.build_tool_result_message = ContextBuilder(settings.llm).build_tool_result_message

    # Mock skill registry — tool returns a result string
    mock_registry = MagicMock()
    mock_registry.get_combined_system_context.return_value = ""
    mock_registry.get_all_tools_schema.return_value = [
        {"type": "function", "function": {"name": "list_workflows", "description": "List workflows"}}
    ]
    mock_registry.execute_tool = AsyncMock(return_value="No workflows found.")
    router._skills = mock_registry

    events = []
    async for event in router.stream_response(_make_inbound(), _make_session()):
        events.append(event)

    # Should have: tool_start, tool_end, chunk(s), done
    types = [e["type"] for e in events]
    assert "tool_start" in types
    assert "tool_end" in types
    assert "done" in types
    assert "error" not in types

    done_event = next(e for e in events if e["type"] == "done")
    assert "workflows" in done_event["content"].lower()

    # LLM was called exactly twice (round 1: tool call; round 2: text)
    assert call_count == 2


@pytest.mark.asyncio
async def test_streaming_tool_result_message_uses_null_content():
    """Assistant tool-call messages must use content=None, not content=''."""
    from steelclaw.llm.context import ContextBuilder
    from steelclaw.settings import LLMSettings

    ctx = ContextBuilder(LLMSettings())
    tc = ToolCall(id="call_xyz", name="some_tool", arguments={})
    msg = ctx.build_assistant_tool_call_message(content="", tool_calls=[tc])

    # content must be None when empty — not "" — to satisfy OpenAI spec and
    # ensure LiteLLM correctly transforms tool-call messages for all providers.
    assert msg["content"] is None
    assert len(msg["tool_calls"]) == 1
    assert msg["tool_calls"][0]["id"] == "call_xyz"


@pytest.mark.asyncio
async def test_tool_name_not_doubled_from_streaming_buffer():
    """The first streaming chunk initialises the buffer AND the update block runs —
    previously this doubled the name (web_search → web_searchweb_search)."""
    from steelclaw.agents.router import AgentRouter
    from steelclaw.settings import AgentSettings

    settings = AgentSettings()
    router = AgentRouter(settings)

    call_count = 0

    async def fake_stream(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            for chunk in _tool_chunk("web_search", "call_123", '{"query":"test"}'):
                yield chunk
        else:
            yield _text_chunk("Done.")

    router._provider = MagicMock()
    router._provider.stream = fake_stream

    router._context = MagicMock()
    router._context.build = AsyncMock(return_value=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "search test"},
    ])
    router._context._build_user_message = lambda t, a=None: {"role": "user", "content": t}
    ctx = ContextBuilder(settings.llm)
    router._context.build_assistant_tool_call_message = ctx.build_assistant_tool_call_message
    router._context.build_tool_result_message = ctx.build_tool_result_message

    executed_names = []

    async def mock_execute_tool(name, args):
        executed_names.append(name)
        return "Search results here."

    mock_registry = MagicMock()
    mock_registry.get_combined_system_context.return_value = ""
    mock_registry.get_all_tools_schema.return_value = []
    mock_registry.execute_tool = mock_execute_tool
    router._skills = mock_registry

    events = []
    async for event in router.stream_response(_make_inbound("search test"), _make_session()):
        events.append(event)

    # Tool must be called with the correct (non-doubled) name
    assert executed_names == ["web_search"], f"Got: {executed_names}"
    done = next(e for e in events if e["type"] == "done")
    assert "Done" in done["content"]


@pytest.mark.asyncio
async def test_execute_tool_call_guards_none_result():
    """_execute_tool_call must return a string even when the executor returns None."""
    settings = AgentSettings()
    router = AgentRouter(settings)

    mock_registry = MagicMock()
    mock_registry.execute_tool = AsyncMock(return_value=None)
    router._skills = mock_registry

    tc = ToolCall(id="call_1", name="broken_tool", arguments={})
    result = await router._execute_tool_call(tc)

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_tool_start_event_includes_skill_and_label():
    """tool_start events must include 'skill', 'label', and 'id' fields.
    tool_end events must include 'id' and 'duration_ms' fields.
    """
    settings = AgentSettings()
    router = AgentRouter(settings)

    call_count = 0

    async def fake_stream(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            for chunk in _tool_chunk("web_search", "call_skill_test", '{"query":"test"}'):
                yield chunk
        else:
            yield _text_chunk("Result.")

    router._provider = MagicMock()
    router._provider.stream = fake_stream

    router._context = MagicMock()
    router._context.build = AsyncMock(return_value=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "search"},
    ])
    router._context._build_user_message = lambda t, a=None: {"role": "user", "content": t}
    from steelclaw.llm.context import ContextBuilder
    ctx = ContextBuilder(settings.llm)
    router._context.build_assistant_tool_call_message = ctx.build_assistant_tool_call_message
    router._context.build_tool_result_message = ctx.build_tool_result_message

    # Mock registry with a skill that has a description
    mock_skill = MagicMock()
    mock_skill.name = "web_search"
    mock_skill.metadata = MagicMock()
    mock_skill.metadata.description = "Search the web for information"

    mock_registry = MagicMock()
    mock_registry.get_combined_system_context.return_value = ""
    mock_registry.get_all_tools_schema.return_value = []
    mock_registry.get_skill_for_tool.return_value = mock_skill
    mock_registry.execute_tool = AsyncMock(return_value="Search results.")
    router._skills = mock_registry

    events = []
    async for event in router.stream_response(_make_inbound("search"), _make_session()):
        events.append(event)

    tool_start = next((e for e in events if e["type"] == "tool_start"), None)
    tool_end = next((e for e in events if e["type"] == "tool_end"), None)

    assert tool_start is not None, "Expected a tool_start event"
    assert tool_start.get("skill") == "web_search"
    assert tool_start.get("label") == "Search the web for information"
    assert tool_start.get("id") == "call_skill_test"

    assert tool_end is not None, "Expected a tool_end event"
    assert tool_end.get("id") == "call_skill_test"
    assert isinstance(tool_end.get("duration_ms"), int)
    assert tool_end.get("duration_ms") >= 0


@pytest.mark.asyncio
async def test_on_tool_event_callback_called_for_non_streaming():
    """on_tool_event callback must be invoked for tool_start/end in route_with_usage."""
    settings = AgentSettings()
    router = AgentRouter(settings)

    async def fake_complete(messages, tools=None, **kwargs):
        from steelclaw.llm.provider import LLMResponse
        call_count = getattr(fake_complete, "_calls", 0) + 1
        fake_complete._calls = call_count
        if call_count == 1:
            return LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="call_cb_1", name="calc", arguments={})],
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="test-model",
                finish_reason="tool_calls",
            )
        return LLMResponse(
            content="Computed.",
            tool_calls=[],
            usage={"prompt_tokens": 5, "completion_tokens": 3},
            model="test-model",
            finish_reason="stop",
        )

    router._provider = MagicMock()
    router._provider.complete = fake_complete

    router._context = MagicMock()
    router._context.build = AsyncMock(return_value=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "compute"},
    ])
    router._context._build_user_message = lambda t, a=None: {"role": "user", "content": t}
    from steelclaw.llm.context import ContextBuilder
    ctx = ContextBuilder(settings.llm)
    router._context.build_assistant_tool_call_message = ctx.build_assistant_tool_call_message
    router._context.build_tool_result_message = ctx.build_tool_result_message

    mock_skill = MagicMock()
    mock_skill.name = "calculator"
    mock_skill.metadata = MagicMock()
    mock_skill.metadata.description = "Perform calculations"

    mock_registry = MagicMock()
    mock_registry.get_combined_system_context.return_value = ""
    mock_registry.get_all_tools_schema.return_value = []
    mock_registry.get_skill_for_tool.return_value = mock_skill
    mock_registry.execute_tool = AsyncMock(return_value="42")
    router._skills = mock_registry

    received_events = []

    async def _on_tool_event(event):
        received_events.append(event)

    inbound = _make_inbound("compute")
    session = _make_session()
    await router.route_with_usage(inbound, session, on_tool_event=_on_tool_event)

    types = [e["type"] for e in received_events]
    assert "tool_start" in types
    assert "tool_end" in types

    start = next(e for e in received_events if e["type"] == "tool_start")
    assert start["name"] == "calc"
    assert start["skill"] == "calculator"
    assert start["label"] == "Perform calculations"

    end = next(e for e in received_events if e["type"] == "tool_end")
    assert end["name"] == "calc"
    assert isinstance(end["duration_ms"], int)
