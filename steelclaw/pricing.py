"""Model pricing constants for cost calculation."""

from __future__ import annotations

# Prices in USD per 1K tokens: {"model": {"prompt": price, "completion": price}}
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude (Anthropic)
    "claude-opus-4-20250514": {"prompt": 0.015, "completion": 0.075},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
    "claude-haiku-4-20250514": {"prompt": 0.0008, "completion": 0.004},
    # OpenAI
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "o1": {"prompt": 0.015, "completion": 0.06},
    "o1-mini": {"prompt": 0.003, "completion": 0.012},
    "o3-mini": {"prompt": 0.0011, "completion": 0.0044},
    # Google Gemini
    "gemini/gemini-pro": {"prompt": 0.00025, "completion": 0.0005},
    "gemini/gemini-1.5-pro": {"prompt": 0.00125, "completion": 0.005},
    "gemini/gemini-1.5-flash": {"prompt": 0.000075, "completion": 0.0003},
    # DeepSeek
    "deepseek/deepseek-chat": {"prompt": 0.00014, "completion": 0.00028},
    "deepseek/deepseek-coder": {"prompt": 0.00014, "completion": 0.00028},
}

# Fallback pricing for unknown models
_DEFAULT_PRICING = {"prompt": 0.001, "completion": 0.002}


def calculate_cost(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float:
    """Calculate estimated cost in USD for a given model and token counts."""
    if not prompt_tokens and not completion_tokens:
        return 0.0

    pricing = MODEL_PRICING.get(model or "", _DEFAULT_PRICING)
    prompt_cost = ((prompt_tokens or 0) / 1000) * pricing["prompt"]
    completion_cost = ((completion_tokens or 0) / 1000) * pricing["completion"]
    return round(prompt_cost + completion_cost, 6)
