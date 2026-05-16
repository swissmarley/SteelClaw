"""LLM provider abstraction via LiteLLM — supports Claude, OpenAI, DeepSeek, and more."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from steelclaw.settings import LLMSettings

logger = logging.getLogger("steelclaw.llm")


class LLMProvider:
    """Async wrapper around LiteLLM for multi-provider LLM completion."""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        self._configure_keys()

    def _configure_keys(self) -> None:
        """Push provider API keys into env vars where LiteLLM expects them."""
        if self._settings.api_key:
            os.environ.setdefault("OPENAI_API_KEY", self._settings.api_key)

        for provider, key in self._settings.provider_keys.items():
            env_var = f"{provider.upper()}_API_KEY"
            os.environ.setdefault(env_var, key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Non-streaming completion. Returns the full response at once."""
        import litellm

        model = model or self._settings.default_model
        temperature = temperature if temperature is not None else self._settings.temperature
        max_tokens = max_tokens or self._settings.max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": self._settings.timeout,
        }
        if self._settings.api_base:
            kwargs["api_base"] = self._settings.api_base
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        logger.debug("LLM request: model=%s, messages=%d, tools=%d",
                      model, len(messages), len(tools or []))

        response = await litellm.acompletion(**kwargs)
        return LLMResponse.from_litellm(response)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming completion. Yields chunks as they arrive."""
        import litellm

        model = model or self._settings.default_model
        temperature = temperature if temperature is not None else self._settings.temperature
        max_tokens = max_tokens or self._settings.max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": self._settings.timeout,
            "stream": True,
        }
        if self._settings.api_base:
            kwargs["api_base"] = self._settings.api_base
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            yield StreamChunk.from_litellm_chunk(chunk)


class LLMResponse:
    """Normalised LLM response."""

    def __init__(
        self,
        content: str | None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str | None = None,
        model: str | None = None,
        usage: dict | None = None,
    ) -> None:
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.model = model
        self.usage = usage or {}

    @classmethod
    def from_litellm(cls, response: Any) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args_str = tc.function.arguments
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {"raw": args_str}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return cls(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            model=getattr(response, "model", None),
            usage=dict(getattr(response, "usage", {})) if hasattr(response, "usage") else {},
        )


class StreamChunk:
    """A single chunk from a streaming LLM response."""

    def __init__(
        self,
        content: str | None = None,
        tool_call_delta: dict | None = None,
        finish_reason: str | None = None,
        model: str | None = None,
        usage: dict | None = None,
    ) -> None:
        self.content = content or ""
        self.tool_call_delta = tool_call_delta
        self.finish_reason = finish_reason
        self.model = model
        self.usage = usage

    @classmethod
    def from_litellm_chunk(cls, chunk: Any) -> StreamChunk:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            return cls(finish_reason="stop")

        tool_delta = None
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            tc = delta.tool_calls[0]
            tool_delta = {
                "index": tc.index,
                "id": getattr(tc, "id", None),
                "name": getattr(tc.function, "name", None) if hasattr(tc, "function") else None,
                "arguments": getattr(tc.function, "arguments", "") if hasattr(tc, "function") else "",
            }

        # Extract model and usage from chunk (litellm includes these on the final chunk)
        model = getattr(chunk, "model", None)
        usage = None
        if hasattr(chunk, "usage") and chunk.usage is not None:
            usage = dict(chunk.usage)

        return cls(
            content=getattr(delta, "content", None),
            tool_call_delta=tool_delta,
            finish_reason=chunk.choices[0].finish_reason,
            model=model,
            usage=usage,
        )


class ToolCall:
    """A normalised tool/function call from the LLM."""

    def __init__(self, id: str, name: str, arguments: dict) -> None:
        self.id = id
        self.name = name
        self.arguments = arguments

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}
