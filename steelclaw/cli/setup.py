"""Interactive onboarding wizard — guides user through SteelClaw setup."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def run_setup() -> None:
    """Full interactive setup wizard."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
    from rich.table import Table
    from rich.text import Text

    console = Console()

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
        "Your settings will be saved to [bold]config.json[/bold].\n"
        "You can change anything later via the web dashboard or by editing the file.[/dim]\n"
    )

    total_steps = 7
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
        },
    }

    # ── Step 1: LLM Provider ────────────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 1 of {total_steps}:[/bold] LLM Provider Configuration",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    providers = Table(show_header=True, box=box.SIMPLE_HEAD)
    providers.add_column("#", style="bold", width=3)
    providers.add_column("Provider", style="cyan")
    providers.add_column("Example Model", style="dim")
    providers.add_column("Env Var", style="dim")
    providers.add_row("1", "Anthropic (Claude)", "claude-sonnet-4-20250514", "ANTHROPIC_API_KEY")
    providers.add_row("2", "OpenAI", "gpt-4o", "OPENAI_API_KEY")
    providers.add_row("3", "DeepSeek", "deepseek/deepseek-chat", "DEEPSEEK_API_KEY")
    providers.add_row("4", "Ollama (local)", "ollama/llama3", "None")
    providers.add_row("5", "Other (custom)", "model-name", "Varies")
    console.print(providers)
    console.print()

    choice = Prompt.ask(
        "[cyan]Select your LLM provider[/cyan]",
        choices=["1", "2", "3", "4", "5"],
        default="1",
    )

    llm_config: Dict[str, Any] = {
        "temperature": 0.7,
        "max_tokens": 4096,
        "max_context_messages": 50,
        "streaming": True,
        "timeout": 120,
    }

    provider_map = {
        "1": ("claude-sonnet-4-20250514", "ANTHROPIC_API_KEY", "anthropic"),
        "2": ("gpt-4o", "OPENAI_API_KEY", "openai"),
        "3": ("deepseek/deepseek-chat", "DEEPSEEK_API_KEY", "deepseek"),
        "4": ("ollama/llama3", None, None),
        "5": (None, None, None),
    }

    default_model, env_var, provider_name = provider_map[choice]
    api_key_to_test = None

    if choice == "5":
        default_model = Prompt.ask("[cyan]Enter the model identifier[/cyan]")
        env_var = Prompt.ask("[cyan]Enter the API key env var name[/cyan] [dim](or leave blank)[/dim]", default="")
        if not env_var:
            env_var = None

    if choice == "4":
        console.print("[dim]Ollama runs locally — no API key needed.[/dim]")
        console.print("[dim]Make sure Ollama is running: ollama serve[/dim]")
        llm_config["api_base"] = Prompt.ask(
            "[cyan]Ollama API base URL[/cyan]",
            default="http://localhost:11434",
        )
        model = Prompt.ask("[cyan]Model name[/cyan]", default=default_model)
    else:
        model = Prompt.ask("[cyan]Model[/cyan]", default=default_model)

        if env_var:
            existing_key = os.environ.get(env_var, "")
            if existing_key:
                masked = existing_key[:8] + "..." + existing_key[-4:]
                console.print(f"[green]Found existing {env_var}:[/green] {masked}")
                use_existing = Confirm.ask("[cyan]Use this key?[/cyan]", default=True)
                if use_existing:
                    api_key_to_test = existing_key
                else:
                    existing_key = ""

            if not existing_key:
                api_key = Prompt.ask(
                    f"[cyan]Enter your API key[/cyan] [dim]({env_var})[/dim]",
                    password=True,
                )
                if api_key:
                    llm_config["api_key"] = api_key
                    api_key_to_test = api_key
                    if provider_name:
                        llm_config.setdefault("provider_keys", {})[provider_name] = api_key

    llm_config["default_model"] = model

    # ── Advanced LLM settings ──────────────────────────────────────────
    if Confirm.ask("\n[cyan]Configure advanced LLM settings?[/cyan] [dim](temperature, tokens, etc.)[/dim]", default=False):
        llm_config["temperature"] = FloatPrompt.ask(
            "[cyan]Temperature[/cyan] [dim](0.0 = precise, 2.0 = creative)[/dim]",
            default=0.7,
        )
        llm_config["max_tokens"] = IntPrompt.ask(
            "[cyan]Max output tokens[/cyan]",
            default=4096,
        )
        llm_config["max_context_messages"] = IntPrompt.ask(
            "[cyan]Max context messages[/cyan] [dim](history messages per request)[/dim]",
            default=50,
        )
        llm_config["timeout"] = IntPrompt.ask(
            "[cyan]Request timeout (seconds)[/cyan]",
            default=120,
        )

    system_prompt = (
        "You are SteelClaw, a helpful personal AI assistant. "
        "You can execute commands, browse the web, manage tasks, and communicate across platforms. "
        "Be concise, accurate, and proactive."
    )
    if Confirm.ask("\n[cyan]Customize the system prompt?[/cyan]", default=False):
        system_prompt = Prompt.ask("[cyan]System prompt[/cyan]", default=system_prompt)
    llm_config["system_prompt"] = system_prompt

    # ── Quick test ────────────────────────────────────────────────────
    if api_key_to_test and Confirm.ask("\n[cyan]Test the API key now?[/cyan]", default=True):
        _test_api_key(console, model, api_key_to_test, provider_name, llm_config.get("api_base"))

    config["agents"]["llm"] = llm_config
    console.print("[green]LLM configured.[/green]\n")

    # ── Step 2: Server & Database ────────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 2 of {total_steps}:[/bold] Server & Database",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    port = IntPrompt.ask("[cyan]Server port[/cyan]", default=8000)
    config["server"]["port"] = port

    if Confirm.ask("[cyan]Bind to all interfaces (0.0.0.0)?[/cyan]", default=True):
        config["server"]["host"] = "0.0.0.0"
    else:
        config["server"]["host"] = "127.0.0.1"

    if Confirm.ask("[cyan]Configure database?[/cyan] [dim](default: SQLite in ./data/)[/dim]", default=False):
        db_url = Prompt.ask(
            "[cyan]Database URL[/cyan]",
            default="sqlite+aiosqlite:///./data/steelclaw.db",
        )
        config["database"]["url"] = db_url

    console.print("[green]Server & database configured.[/green]\n")

    # ── Step 3: Messaging Platforms ─────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 3 of {total_steps}:[/bold] Messaging Platforms",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()
    console.print("[dim]Connect SteelClaw to your messaging apps.[/dim]")
    console.print("[dim]WebSocket chat (web UI + CLI) is always available.[/dim]\n")

    platform_configs = {
        "telegram": {"prompt": "Telegram Bot Token", "key": "token", "hint": "Get from @BotFather on Telegram"},
        "discord": {"prompt": "Discord Bot Token", "key": "token", "hint": "From Discord Developer Portal"},
        "slack": {"prompt": "Slack Bot Token", "key": "token", "hint": "From Slack App settings (xoxb-...)"},
        "whatsapp": {"prompt": "WhatsApp Access Token", "key": "token", "hint": "From Meta Business Suite"},
        "matrix": {"prompt": "Matrix Access Token", "key": "token", "hint": "From Element or matrix-commander"},
    }

    for platform, info in platform_configs.items():
        if Confirm.ask(f"[cyan]Enable {platform.title()}?[/cyan]", default=False):
            console.print(f"  [dim]{info['hint']}[/dim]")
            token = Prompt.ask(f"[cyan]{info['prompt']}[/cyan]", password=True)
            connector_cfg: Dict[str, Any] = {"enabled": True, info["key"]: token}
            if platform == "matrix":
                hs = Prompt.ask("[cyan]Matrix homeserver URL[/cyan]", default="https://matrix.org")
                uid = Prompt.ask("[cyan]Matrix user ID[/cyan]", default="@steelclaw:matrix.org")
                connector_cfg["homeserver"] = hs
                connector_cfg["user_id"] = uid
            config["gateway"]["connectors"][platform] = connector_cfg
            console.print(f"[green]{platform.title()} enabled.[/green]")
        console.print()

    # ── Step 4: Gateway Settings ─────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 4 of {total_steps}:[/bold] Gateway & Mention Settings",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    console.print("[dim]In group chats, SteelClaw only responds when mentioned or triggered by keyword.[/dim]")
    keywords_str = Prompt.ask(
        "[cyan]Mention keywords[/cyan] [dim](comma-separated)[/dim]",
        default="@steelclaw, @sc",
    )
    config["gateway"]["mention_keywords"] = [k.strip() for k in keywords_str.split(",") if k.strip()]

    if Confirm.ask("[cyan]Enable DM allowlist?[/cyan] [dim](only approved users can DM)[/dim]", default=False):
        config["gateway"]["dm_allowlist_enabled"] = True
    else:
        config["gateway"]["dm_allowlist_enabled"] = False

    console.print("[green]Gateway configured.[/green]\n")

    # ── Step 5: Security ────────────────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 5 of {total_steps}:[/bold] Security Settings",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    console.print("[dim]When SteelClaw wants to run a shell command:[/dim]")
    perm_table = Table(show_header=False, box=None, padding=(0, 2))
    perm_table.add_column(style="bold", width=10)
    perm_table.add_column(style="dim")
    perm_table.add_row("ask", "Prompt you for approval each time (safest)")
    perm_table.add_row("record", "Log the command but allow it")
    perm_table.add_row("ignore", "Auto-allow everything (use with caution)")
    console.print(perm_table)
    console.print()

    perm = Prompt.ask(
        "[cyan]Default permission level[/cyan]",
        choices=["ask", "record", "ignore"],
        default="ask",
    )
    config["agents"]["security"]["default_permission"] = perm

    if Confirm.ask("[cyan]Enable sandboxed execution?[/cyan] [dim](recommended)[/dim]", default=True):
        config["agents"]["security"]["sandbox_enabled"] = True
    else:
        config["agents"]["security"]["sandbox_enabled"] = False

    timeout = IntPrompt.ask("[cyan]Max command timeout (seconds)[/cyan]", default=30)
    config["agents"]["security"]["max_command_timeout"] = timeout

    console.print("[green]Security configured.[/green]\n")

    # ── Step 6: Scheduler ──────────────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 6 of {total_steps}:[/bold] Background Scheduler",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    if Confirm.ask("[cyan]Enable background scheduler?[/cyan] [dim](cron jobs, reminders)[/dim]", default=True):
        config["agents"]["scheduler"]["enabled"] = True
        tz = Prompt.ask("[cyan]Timezone[/cyan] [dim](e.g. UTC, US/Eastern, Europe/London)[/dim]", default="UTC")
        config["agents"]["scheduler"]["timezone"] = tz
        max_jobs = IntPrompt.ask("[cyan]Max concurrent jobs[/cyan]", default=5)
        config["agents"]["scheduler"]["max_concurrent_jobs"] = max_jobs
    else:
        config["agents"]["scheduler"]["enabled"] = False

    console.print("[green]Scheduler configured.[/green]\n")

    # ── Step 7: Voice & Extras ──────────────────────────────────────────
    console.print(Panel(
        f"[bold]Step 7 of {total_steps}:[/bold] Voice & Optional Features",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()

    if Confirm.ask("[cyan]Enable voice capabilities?[/cyan] [dim](requires OpenAI API key)[/dim]", default=False):
        config["agents"]["voice"]["enabled"] = True
        stt = Prompt.ask("[cyan]Transcription model[/cyan]", default="whisper-1")
        config["agents"]["voice"]["transcription_model"] = stt
        tts = Prompt.ask("[cyan]TTS model[/cyan]", default="tts-1")
        config["agents"]["voice"]["tts_model"] = tts
        voice_choice = Prompt.ask(
            "[cyan]TTS voice[/cyan]",
            choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            default="alloy",
        )
        config["agents"]["voice"]["tts_voice"] = voice_choice
    else:
        config["agents"]["voice"]["enabled"] = False

    if Confirm.ask("[cyan]Customize skill directories?[/cyan]", default=False):
        config["agents"]["skills"]["global_dir"] = Prompt.ask(
            "[cyan]Global skills directory[/cyan]",
            default="~/.steelclaw/skills",
        )
        config["agents"]["skills"]["workspace_dir"] = Prompt.ask(
            "[cyan]Workspace skills directory[/cyan]",
            default=".steelclaw/skills",
        )

    console.print("[green]Configuration complete![/green]\n")

    # ── Summary ─────────────────────────────────────────────────────────
    summary = Table(title="Configuration Summary", box=box.ROUNDED, border_style="blue")
    summary.add_column("Setting", style="cyan", width=20)
    summary.add_column("Value")

    summary.add_row("LLM Model", config["agents"]["llm"].get("default_model", "—"))
    summary.add_row("Temperature", str(config["agents"]["llm"].get("temperature", "0.7")))
    summary.add_row("Max Tokens", str(config["agents"]["llm"].get("max_tokens", "4096")))
    summary.add_row("Server", f"{config['server']['host']}:{config['server']['port']}")
    summary.add_row("Database", config["database"]["url"][:50])
    connectors = [k for k, v in config["gateway"]["connectors"].items() if v.get("enabled")]
    summary.add_row("Platforms", ", ".join(connectors) if connectors else "WebSocket only")
    summary.add_row("Mention Keywords", ", ".join(config["gateway"]["mention_keywords"]))
    summary.add_row("DM Allowlist", str(config["gateway"]["dm_allowlist_enabled"]))
    summary.add_row("Security", config["agents"]["security"]["default_permission"])
    summary.add_row("Sandbox", str(config["agents"]["security"]["sandbox_enabled"]))
    summary.add_row("Cmd Timeout", f"{config['agents']['security']['max_command_timeout']}s")
    sched = config["agents"]["scheduler"]
    summary.add_row("Scheduler", f"{sched['enabled']} ({sched.get('timezone', 'UTC')})" if sched["enabled"] else "Disabled")
    summary.add_row("Voice", str(config["agents"]["voice"]["enabled"]))
    console.print(summary)
    console.print()

    # ── Write config ────────────────────────────────────────────────────
    config_path = Path("config.json")
    if config_path.exists():
        if not Confirm.ask(
            f"[yellow]{config_path} already exists. Overwrite?[/yellow]",
            default=False,
        ):
            alt = Prompt.ask("[cyan]Save as[/cyan]", default="config.new.json")
            config_path = Path(alt)

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"\n[green]Saved to {config_path}[/green]")

    # ── Next Steps ──────────────────────────────────────────────────────
    console.print()
    next_steps = Panel(
        "[bold]Start the server:[/bold]\n"
        "  steelclaw serve\n\n"
        "[bold]Open the Control Dashboard:[/bold]\n"
        "  http://localhost:{port}/\n\n"
        "[bold]Or chat from the terminal:[/bold]\n"
        "  steelclaw chat\n\n"
        "[bold]API Documentation:[/bold]\n"
        "  http://localhost:{port}/docs\n\n"
        "[dim]Edit config.json anytime or use the web dashboard to change settings.\n"
        "Run [bold]steelclaw setup[/bold] again to reconfigure.[/dim]".format(port=port),
        title="[bold green]Next Steps[/bold green]",
        border_style="green",
        box=box.DOUBLE,
    )
    console.print(next_steps)


def _test_api_key(console, model: str, api_key: str, provider: str | None, api_base: str | None) -> None:
    """Quick validation of the API key by making a tiny request."""
    from rich.console import Console

    try:
        console.print("[dim]Testing API key...[/dim]", end=" ")
        import httpx

        # Build the test based on provider
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
        elif provider == "openai" or provider == "deepseek":
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
        elif resp.status_code == 403:
            console.print("[red]Access denied (403 Forbidden)[/red]")
        else:
            console.print(f"[yellow]Got status {resp.status_code} — key may still work[/yellow]")
    except ImportError:
        console.print("[yellow]Skipped (httpx not available)[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Could not test: {e}[/yellow]")
