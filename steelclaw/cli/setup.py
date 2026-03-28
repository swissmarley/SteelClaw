"""Interactive onboarding wizard — guides user through SteelClaw setup."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


# Model lists grouped by provider
PROVIDER_MODELS = {
    "Anthropic (Claude)": {
        "env_var": "ANTHROPIC_API_KEY",
        "provider_key": "anthropic",
        "models": [
            ("Claude Sonnet 4.6", "claude-sonnet-4-20250514"),
            ("Claude Opus 4.6", "claude-opus-4-20250514"),
            ("Claude Sonnet 4.5", "claude-sonnet-4-5-20250514"),
            ("Claude Opus 4.5", "claude-opus-4-5-20250514"),
            ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
        ],
    },
    "OpenAI": {
        "env_var": "OPENAI_API_KEY",
        "provider_key": "openai",
        "models": [
            ("GPT-5.4", "gpt-5.4"),
            ("GPT-5.4 Pro", "gpt-5.4-pro"),
            ("GPT-5.3-Codex", "gpt-5.3-codex"),
            ("GPT-5.4 Mini", "gpt-5.4-mini"),
            ("GPT-5.3", "gpt-5.3"),
        ],
    },
    "Google Gemini": {
        "env_var": "GOOGLE_API_KEY",
        "provider_key": "google",
        "models": [
            ("Gemini Pro 3.1", "gemini/gemini-pro-3.1"),
            ("Gemini Flash 3.0", "gemini/gemini-flash-3.0"),
        ],
    },
    "Ollama (local)": {
        "env_var": None,
        "provider_key": None,
        "models": [
            ("Llama 3", "ollama/llama3"),
            ("Mistral", "ollama/mistral"),
            ("CodeLlama", "ollama/codellama"),
        ],
    },
    "Custom / Other": {
        "env_var": None,
        "provider_key": None,
        "models": [],
    },
}


def run_setup(reset: bool = False) -> None:
    """Full interactive setup wizard with arrow-key selection."""
    import questionary
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text

    console = Console()
    config_path = Path("config.json")

    if reset and config_path.exists():
        config_path.unlink()
        console.print("[yellow]Existing config.json removed[/yellow]\n")

    # ── Welcome ─────────────────────────────────────────────────────────
    banner = Text()
    banner.append("\n  ____  _             _  ____ _\n", style="bold blue")
    banner.append(" / ___|| |_ ___  ___| |/ ___| | __ ___      __\n", style="bold blue")
    banner.append(" \\___ \\| __/ _ \\/ _ \\ | |   | |/ _` \\ \\ /\\ / /\n", style="bold blue")
    banner.append("  ___) | ||  __/  __/ | |___| | (_| |\\ V  V /\n", style="bold blue")
    banner.append(" |____/ \\__\\___|\\___|_|\\____|_|\\__,_| \\_/\\_/\n", style="bold blue")
    console.print(Panel(
        banner,
        title="[bold]Welcome to SteelClaw Setup[/bold]",
        border_style="blue",
        box=box.DOUBLE,
        padding=(0, 1),
    ))
    console.print()
    console.print(
        "[dim]This wizard will walk you through configuring SteelClaw.\n"
        "Use arrow keys to select options. Press Enter to confirm.\n"
        "Your settings will be saved to [bold]config.json[/bold].[/dim]\n"
    )

    config: Dict[str, Any] = {
        "database": {"url": "sqlite+aiosqlite:///./data/steelclaw.db", "echo": False},
        "server": {"host": "0.0.0.0", "port": 8000, "log_level": "info"},
        "gateway": {"mention_keywords": ["@steelclaw", "@sc"], "dm_allowlist_enabled": False, "connectors": {}},
        "agents": {
            "default_agent": "general",
            "llm": {},
            "skills": {"bundled_dir": "steelclaw/skills/bundled", "global_dir": "~/.steelclaw/skills", "workspace_dir": ".steelclaw/skills", "enabled": True},
            "security": {"approvals_file": "exec-approvals.json", "default_permission": "ask", "sandbox_enabled": True, "max_command_timeout": 30, "blocked_commands": ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"]},
            "scheduler": {"enabled": True, "timezone": "UTC", "max_concurrent_jobs": 5},
            "voice": {"enabled": False, "transcription_model": "whisper-1", "tts_model": "tts-1", "tts_voice": "alloy"},
            "memory": {"enabled": True, "chromadb_path": "~/.steelclaw/chromadb", "collection_name": "steelclaw_memory", "top_k": 5},
        },
    }

    llm_config: Dict[str, Any] = {
        "temperature": 0.7,
        "max_tokens": 4096,
        "max_context_messages": 50,
        "streaming": True,
        "timeout": 120,
    }

    # ── Step 1: LLM Provider (arrow-key selection) ───────────────────
    console.print(Panel("[bold]Step 1:[/bold] LLM Provider Configuration", border_style="cyan", box=box.ROUNDED))

    provider_name = questionary.select(
        "Select your LLM provider:",
        choices=list(PROVIDER_MODELS.keys()),
    ).ask()
    if provider_name is None:
        console.print("[red]Setup cancelled[/red]")
        return

    provider = PROVIDER_MODELS[provider_name]

    # Model selection
    if provider["models"]:
        model_choices = [f"{label} ({model_id})" for label, model_id in provider["models"]]
        model_choices.append("Custom model...")
        selected = questionary.select("Select model:", choices=model_choices).ask()
        if selected is None:
            return

        if selected == "Custom model...":
            model = questionary.text("Enter model identifier:").ask()
            if not model:
                return
        else:
            idx = model_choices.index(selected)
            model = provider["models"][idx][1]
    else:
        model = questionary.text("Enter model identifier:").ask()
        if not model:
            return

    llm_config["default_model"] = model

    # API key
    env_var = provider.get("env_var")
    if env_var:
        existing_key = os.environ.get(env_var, "")
        if existing_key:
            masked = existing_key[:8] + "..." + existing_key[-4:]
            console.print(f"[green]Found {env_var}:[/green] {masked}")
            use_existing = questionary.confirm("Use this key?", default=True).ask()
            if not use_existing:
                existing_key = ""

        if not existing_key:
            api_key = questionary.password(f"Enter your API key ({env_var}):").ask()
            if api_key:
                llm_config["api_key"] = api_key
                if provider["provider_key"]:
                    llm_config.setdefault("provider_keys", {})[provider["provider_key"]] = api_key

    if provider_name == "Ollama (local)":
        console.print("[dim]Ollama runs locally — no API key needed. Make sure Ollama is running.[/dim]")
        api_base = questionary.text("Ollama API base URL:", default="http://localhost:11434").ask()
        if api_base:
            llm_config["api_base"] = api_base

    # Temperature (selection-based)
    temp_choice = questionary.select(
        "Temperature preset:",
        choices=[
            "Creative (0.9)",
            "Balanced (0.7)",
            "Precise (0.3)",
            "Deterministic (0.0)",
        ],
        default="Balanced (0.7)",
    ).ask()
    if temp_choice:
        llm_config["temperature"] = float(temp_choice.split("(")[1].rstrip(")"))

    config["agents"]["llm"] = llm_config
    console.print("[green]LLM configured.[/green]\n")

    # ── Step 2: Server ───────────────────────────────────────────────
    console.print(Panel("[bold]Step 2:[/bold] Server & Database", border_style="cyan", box=box.ROUNDED))

    port = questionary.text("Server port:", default="8000").ask()
    config["server"]["port"] = int(port) if port else 8000

    bind = questionary.select(
        "Bind to:",
        choices=["All interfaces (0.0.0.0)", "Localhost only (127.0.0.1)"],
        default="All interfaces (0.0.0.0)",
    ).ask()
    config["server"]["host"] = "127.0.0.1" if bind and "Localhost" in bind else "0.0.0.0"

    console.print("[green]Server configured.[/green]\n")

    # ── Step 3: Messaging Platforms ──────────────────────────────────
    console.print(Panel("[bold]Step 3:[/bold] Messaging Platforms", border_style="cyan", box=box.ROUNDED))
    console.print("[dim]WebSocket chat (web UI + CLI) is always available.[/dim]\n")

    platforms = questionary.checkbox(
        "Enable messaging platforms:",
        choices=["Telegram", "Discord", "Slack", "WhatsApp", "Matrix"],
    ).ask()

    platform_key_map = {
        "Telegram": ("telegram", "Telegram Bot Token (from @BotFather)"),
        "Discord": ("discord", "Discord Bot Token"),
        "Slack": ("slack", "Slack Bot Token (xoxb-...)"),
        "WhatsApp": ("whatsapp", "WhatsApp Access Token"),
        "Matrix": ("matrix", "Matrix Access Token"),
    }

    for platform in (platforms or []):
        key, prompt = platform_key_map[platform]
        token = questionary.password(f"{prompt}:").ask()
        if token:
            connector_cfg: Dict[str, Any] = {"enabled": True, "token": token}
            config["gateway"]["connectors"][key] = connector_cfg
            console.print(f"[green]{platform} enabled.[/green]")

    console.print()

    # ── Step 4: Security ─────────────────────────────────────────────
    console.print(Panel("[bold]Step 4:[/bold] Security Settings", border_style="cyan", box=box.ROUNDED))

    perm = questionary.select(
        "Default permission for shell commands:",
        choices=[
            "ask — Prompt for approval each time (safest)",
            "record — Log commands but allow",
            "ignore — Auto-allow everything",
        ],
        default="ask — Prompt for approval each time (safest)",
    ).ask()
    if perm:
        config["agents"]["security"]["default_permission"] = perm.split(" — ")[0]

    console.print("[green]Security configured.[/green]\n")

    # ── Step 5: Memory ───────────────────────────────────────────────
    console.print(Panel("[bold]Step 5:[/bold] Memory & Analytics", border_style="cyan", box=box.ROUNDED))

    memory_enabled = questionary.confirm("Enable persistent memory (ChromaDB)?", default=True).ask()
    config["agents"]["memory"]["enabled"] = memory_enabled

    console.print("[green]Memory configured.[/green]\n")

    # ── Summary ──────────────────────────────────────────────────────
    summary = Table(title="Configuration Summary", box=box.ROUNDED, border_style="blue")
    summary.add_column("Setting", style="cyan", width=20)
    summary.add_column("Value")

    summary.add_row("Provider", provider_name)
    summary.add_row("Model", config["agents"]["llm"].get("default_model", "—"))
    summary.add_row("Temperature", str(config["agents"]["llm"].get("temperature", "0.7")))
    summary.add_row("Server", f"{config['server']['host']}:{config['server']['port']}")
    connectors = [k for k, v in config["gateway"]["connectors"].items() if v.get("enabled")]
    summary.add_row("Platforms", ", ".join(connectors) if connectors else "WebSocket only")
    summary.add_row("Security", config["agents"]["security"]["default_permission"])
    summary.add_row("Memory", "Enabled" if memory_enabled else "Disabled")
    console.print(summary)
    console.print()

    # Confirmation
    confirm = questionary.confirm("Save this configuration?", default=True).ask()
    if not confirm:
        console.print("[yellow]Setup cancelled[/yellow]")
        return

    # ── Write config ─────────────────────────────────────────────────
    if config_path.exists() and not reset:
        overwrite = questionary.confirm(f"{config_path} exists. Overwrite?", default=False).ask()
        if not overwrite:
            alt = questionary.text("Save as:", default="config.new.json").ask()
            config_path = Path(alt) if alt else config_path

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"\n[green]Saved to {config_path}[/green]")

    # ── Next Steps ───────────────────────────────────────────────────
    port_val = config["server"]["port"]
    console.print(Panel(
        "[bold]Start the server:[/bold]\n"
        "  steelclaw serve\n\n"
        "[bold]Open the Control Dashboard:[/bold]\n"
        f"  http://localhost:{port_val}/\n\n"
        "[bold]Or chat from the terminal:[/bold]\n"
        "  steelclaw chat\n\n"
        "[bold]Configure agent persona:[/bold]\n"
        "  steelclaw persona\n\n"
        "[dim]Run steelclaw onboard --reset to reconfigure.[/dim]",
        title="[bold green]Next Steps[/bold green]",
        border_style="green",
        box=box.DOUBLE,
    ))


def _test_api_key(console, model: str, api_key: str, provider: str | None, api_base: str | None) -> None:
    """Quick validation of the API key by making a tiny request."""
    try:
        console.print("[dim]Testing API key...[/dim]", end=" ")
        import httpx

        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
                timeout=15,
            )
        elif provider in ("openai", "deepseek"):
            base = api_base or ("https://api.deepseek.com" if provider == "deepseek" else "https://api.openai.com")
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            resp = httpx.post(
                f"{base}/v1/chat/completions",
                headers=headers,
                json={"model": model.replace("deepseek/", ""), "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
                timeout=15,
            )
        else:
            console.print("[yellow]Skipped (unknown provider)[/yellow]")
            return

        if resp.status_code in (200, 201):
            console.print("[green]API key is valid![/green]")
        elif resp.status_code == 401:
            console.print("[red]Invalid API key (401 Unauthorized)[/red]")
        else:
            console.print(f"[yellow]Got status {resp.status_code} — key may still work[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Could not test: {e}[/yellow]")
