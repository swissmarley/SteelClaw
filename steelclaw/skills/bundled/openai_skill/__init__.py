"""OpenAI skill — chat completions and image generation via OpenAI API."""

from __future__ import annotations

import httpx

from steelclaw.skills.credential_store import get_all_credentials

required_credentials = [
    {"key": "api_key", "label": "OpenAI API Key", "type": "password", "test_url": "https://api.openai.com/v1/models"},
]

BASE_URL = "https://api.openai.com/v1"


def _config() -> dict:
    return get_all_credentials("openai_skill")


def _headers() -> dict:
    config = _config()
    api_key = config.get("api_key", "")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


async def tool_chat_completion(
    prompt: str,
    model: str = "gpt-4o",
    system_prompt: str = "",
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request to OpenAI."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure openai_skill"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=_headers(),
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
            )
            resp.raise_for_status()
            data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return f"{content}\n\n_Tokens: {usage.get('prompt_tokens', 0)} in / {usage.get('completion_tokens', 0)} out_"
    except Exception as e:
        return f"Error: {e}"


async def tool_generate_image(
    prompt: str,
    size: str = "1024x1024",
    model: str = "dall-e-3",
) -> str:
    """Generate an image using DALL-E."""
    config = _config()
    if not config.get("api_key"):
        return "Error: API key not configured. Run: steelclaw skills configure openai_skill"
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{BASE_URL}/images/generations",
                headers=_headers(),
                json={"model": model, "prompt": prompt, "size": size, "n": 1},
            )
            resp.raise_for_status()
            data = resp.json()
        images = data.get("data", [])
        if not images:
            return "No image generated."
        img = images[0]
        url = img.get("url", "")
        revised = img.get("revised_prompt", "")
        result = f"Image generated: {url}"
        if revised:
            result += f"\n\nRevised prompt: {revised}"
        return result
    except Exception as e:
        return f"Error: {e}"
