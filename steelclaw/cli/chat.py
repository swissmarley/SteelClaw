"""Interactive TUI chat client — streams responses in real time via WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime


def run_chat(
    server_url: str = "ws://localhost:8000/gateway/ws",
    user_id: str = "cli-user",
) -> None:
    """Entry point for the TUI chat."""
    try:
        asyncio.run(_chat_loop(server_url, user_id))
    except KeyboardInterrupt:
        pass


# ── Spinner frames for animations ──────────────────────────────────────────

THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
TOOL_FRAMES = ["◐", "◓", "◑", "◒"]
CONNECT_FRAMES = ["◜ ", " ◝", " ◞", "◟ "]

# ── Slash commands — grouped for display, flat for autocomplete ────────────

# HELP_SECTIONS drives both the /help table (with section headers) and the
# flat SLASH_COMMANDS list used by the autocompleter.
HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Chat", [
        ("/help",        "Show available commands"),
        ("/exit",        "Exit the chat"),
        ("/quit",        "Exit the chat"),
        ("/clear",       "Clear conversation history"),
        ("/new",         "Start a new conversation"),
        ("/history",     "Show full conversation history"),
        ("/compact",     "Show recent history (last 10 exchanges)"),
        ("/status",      "Connection, server and session info"),
        ("/stats",       "Show session statistics"),
        ("/model",       "Show current model info"),
        ("/version",     "Show SteelClaw version"),
        ("/export",      "Export chat to file  [filename]"),
    ]),
    ("Server / Daemon", [
        ("/serve",       "Start the API server in foreground"),
        ("/start",       "Start SteelClaw as background daemon"),
        ("/stop",        "Stop the background daemon"),
        ("/restart",     "Restart the background daemon"),
        ("/app",         "Manage app  [start|stop|restart|reset]"),
    ]),
    ("Data & Configuration", [
        ("/config",      "View/edit configuration  [show|get <key>|set <key> <val>]"),
        ("/migrate",     "Run database migrations"),
        ("/sessions",    "Manage sessions  [list|reset|delete]"),
        ("/memory",      "Manage memory  [status|search|clear|experiences]"),
        ("/agents",      "Manage agents  [list|add|delete|status]"),
        ("/skills",      "Manage skills  [list|install|enable|disable|configure]"),
        ("/persona",     "Configure agent persona interactively"),
        ("/onboard",     "Run the interactive onboarding wizard"),
        ("/setup",       "Alias for /onboard"),
    ]),
    ("Scheduler", [
        ("/scheduler",   "Manage scheduled jobs  [list|add|remove|run|set-timezone]"),
    ]),
    ("Security", [
        ("/security",    "Security settings  [show|list-rules|add-rule|capabilities]"),
        ("/sudo",        "Sudo mode  [enable|disable|whitelist list|add|remove]"),
    ]),
    ("Infrastructure", [
        ("/logs",        "View daemon logs  [-f to follow]"),
        ("/gateway",     "Manage gateway  [start|stop|restart]"),
        ("/connectors",  "Manage connectors  [list|configure|enable|disable|status]"),
    ]),
    ("Info", [
        ("/pricing",     "Show model pricing table"),
    ]),
]

# Flat list derived from HELP_SECTIONS — used by the autocompleter.
SLASH_COMMANDS: list[tuple[str, str]] = [
    entry for _, cmds in HELP_SECTIONS for entry in cmds
]

# Commands resolved entirely within the chat loop (no subprocess).
_CHAT_NATIVE: frozenset[str] = frozenset({
    "/help", "/exit", "/quit", "/clear", "/status",
    "/history", "/compact", "/model", "/stats", "/new", "/export",
    "/version", "/pricing",
})

# Commands delegated to `steelclaw <subcommand> [args]` as a subprocess.
_CLI_PASSTHROUGH: frozenset[str] = frozenset({
    "/serve", "/start", "/stop", "/restart", "/migrate",
    "/sessions", "/memory", "/agents", "/skills", "/logs",
    "/gateway", "/connectors", "/persona", "/onboard", "/setup",
    "/scheduler", "/security", "/app", "/config",
})

# Commands with custom argument mapping (not simple name→subcommand).
_SPECIAL_CMDS: frozenset[str] = frozenset({
    "/sudo",
})


def _ws_to_http_base(ws_url: str) -> str:
    """Convert a WebSocket URL to its HTTP base (scheme + host + port, no path).

    Uses urllib.parse so the scheme substitution is safe even when the
    protocol string appears elsewhere in the URL (e.g. as part of a hostname).
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    # Keep only scheme + netloc; drop path/query/fragment
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


# ── prompt_toolkit autocomplete ────────────────────────────────────────────

def _build_prompt_session():
    """Return a prompt_toolkit PromptSession with slash-command autocomplete.

    Returns None if prompt_toolkit is unavailable or stdin is not a TTY.
    """
    if not sys.stdin.isatty():
        return None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.styles import Style
        from prompt_toolkit.formatted_text import HTML

        class SlashCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text_before_cursor
                if not text.startswith("/"):
                    return
                # Fuzzy prefix: typed chars after "/" must all appear in order
                typed = text.lower()
                for cmd, desc in SLASH_COMMANDS:
                    if cmd.startswith(typed):
                        display = f"{cmd:<12} {desc}"
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display=display,
                        )

        style = Style.from_dict({
            "prompt":              "bold ansicyan",
            "completion-menu.completion":          "bg:#1a1a2e fg:#e0e0e0",
            "completion-menu.completion.current":  "bg:#16213e fg:#00d4ff bold",
            "completion-menu.meta.completion":     "bg:#1a1a2e fg:#888888",
            "scrollbar.background":                "bg:#1a1a2e",
            "scrollbar.button":                    "bg:#16213e",
        })

        session: PromptSession = PromptSession(
            completer=SlashCompleter(),
            complete_while_typing=True,
            style=style,
            reserve_space_for_menu=6,
        )
        return session
    except ImportError:
        return None


async def _chat_loop(server_url: str, user_id: str) -> None:
    try:
        import websockets
    except ImportError:
        print("Error: websockets package not installed.")
        sys.exit(1)

    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
    from rich import box
    from rich.columns import Columns
    from rich.rule import Rule

    theme = Theme({
        "user": "bold cyan",
        "assistant": "bold green",
        "system": "bold yellow",
        "dim": "dim white",
        "error": "bold red",
        "accent": "bold blue",
        "tool": "bold magenta",
        "hint": "dim italic",
        "success": "bold green",
    })
    console = Console(theme=theme)
    messages: list[dict] = []
    start_time = time.time()
    msg_count = 0

    # Build the prompt_toolkit session (None if non-interactive)
    pt_session = _build_prompt_session()

    def _render_banner() -> None:
        from steelclaw.cli.banner import print_banner
        print_banner()

    def _render_help() -> Panel:
        tbl = Table(show_header=True, box=box.SIMPLE_HEAVY, padding=(0, 2), show_edge=False)
        tbl.add_column("Command", style="accent", min_width=16)
        tbl.add_column("Description", style="dim")

        for i, (section_name, cmds) in enumerate(HELP_SECTIONS):
            if i > 0:
                tbl.add_section()
            # Section header row
            tbl.add_row(f"[dim italic]{section_name}[/]", "", end_section=True)
            for cmd, desc in cmds:
                tbl.add_row(cmd, desc)

        tbl.add_section()
        tbl.add_row("[dim]Ctrl+C[/dim]", "[dim]Exit immediately[/dim]")
        return Panel(tbl, title="[accent] Commands [/]", border_style="blue", box=box.ROUNDED)

    def _render_message(role: str, content: str, ts: str = "") -> Panel:
        if role == "user":
            label = "[user] You [/user]"
            border = "cyan"
        else:
            label = "[assistant] SteelClaw [/assistant]"
            border = "green"

        time_str = f"  [dim]{ts}[/]" if ts else ""
        try:
            body = Markdown(content)
        except Exception:
            body = Text(content)

        return Panel(
            body,
            title=f"{label}{time_str}",
            title_align="left",
            border_style=border,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    async def _render_status(url: str, uid: str, ws_connected: bool) -> Panel:
        # Probe the health endpoint without blocking the event loop
        http_base = _ws_to_http_base(url)
        api_online = False
        api_version = None
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient() as _client:
                _resp = await _client.get(f"{http_base}/health", timeout=2.0)
                if _resp.status_code == 200:
                    api_online = True
                    try:
                        api_version = _resp.json().get("version")
                    except Exception:
                        pass
        except Exception:
            pass

        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim", min_width=14)
        tbl.add_column()
        tbl.add_row("Server", f"[accent]{url}[/]")
        tbl.add_row("User", f"[accent]{uid}[/]")
        ws_str = "[success]● Connected[/]" if ws_connected else "[error]● Disconnected[/]"
        api_str = (
            f"[success]● Online[/] [dim]v{api_version}[/]" if api_online and api_version
            else "[success]● Online[/]" if api_online
            else "[error]● Unreachable[/]"
        )
        tbl.add_row("WebSocket", ws_str)
        tbl.add_row("REST API", api_str)
        tbl.add_row("Mode", "[accent]Streaming[/]")
        uptime = int(time.time() - start_time)
        mins, secs = divmod(uptime, 60)
        tbl.add_row("Uptime", f"[dim]{mins}m {secs}s[/]")
        tbl.add_row("Messages", f"[dim]{msg_count}[/]")
        return Panel(tbl, title="[accent] Status [/]", border_style="blue", box=box.ROUNDED)

    def _render_version(url: str) -> Panel:
        try:
            from importlib.metadata import version as pkg_ver
            v = pkg_ver("steelclaw")
        except Exception:
            try:
                from steelclaw import __version__
                v = __version__
            except Exception:
                v = "unknown"

        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim", min_width=14)
        tbl.add_column()
        tbl.add_row("Package", "[accent]steelclaw[/]")
        tbl.add_row("Version", f"[bold accent]{v}[/]")
        tbl.add_row("Interface", "[accent]WebSocket TUI[/]")
        tbl.add_row("Server", f"[dim]{url}[/]")
        return Panel(tbl, title="[accent] Version [/]", border_style="blue", box=box.ROUNDED)

    def _render_pricing() -> Panel:
        from steelclaw.pricing import MODEL_PRICING

        tbl = Table(show_header=True, box=box.SIMPLE_HEAVY, padding=(0, 2), show_edge=False)
        tbl.add_column("Model", style="accent", min_width=36)
        tbl.add_column("Prompt / 1K", style="green", justify="right", min_width=14)
        tbl.add_column("Completion / 1K", style="yellow", justify="right", min_width=16)

        # Group by provider prefix
        _providers: dict[str, list] = {}
        for model, prices in MODEL_PRICING.items():
            if "/" in model:
                provider = model.split("/")[0].title()
            elif model.startswith("claude"):
                provider = "Anthropic"
            elif model.startswith(("gpt", "o1", "o3")):
                provider = "OpenAI"
            else:
                provider = "Other"
            _providers.setdefault(provider, []).append((model, prices))

        first = True
        for provider, models in _providers.items():
            if not first:
                tbl.add_section()
            first = False
            tbl.add_row(f"[dim italic]{provider}[/]", "", "", end_section=True)
            for model, prices in models:
                short_model = model.split("/")[-1] if "/" in model else model
                tbl.add_row(
                    short_model,
                    f"${prices['prompt']:.5f}",
                    f"${prices['completion']:.5f}",
                )

        return Panel(tbl, title="[accent] Model Pricing (USD) [/]", border_style="blue", box=box.ROUNDED)

    def _render_stats() -> Panel:
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim", min_width=14)
        tbl.add_column()
        uptime = int(time.time() - start_time)
        mins, secs = divmod(uptime, 60)
        tbl.add_row("Session time", f"{mins}m {secs}s")
        tbl.add_row("Messages sent", str(sum(1 for m in messages if m["role"] == "user")))
        tbl.add_row("Responses", str(sum(1 for m in messages if m["role"] == "assistant")))
        total_chars = sum(len(m["content"]) for m in messages if m["role"] == "assistant")
        tbl.add_row("Chars received", f"{total_chars:,}")
        return Panel(tbl, title="[accent] Statistics [/]", border_style="blue", box=box.ROUNDED)

    async def _get_input() -> str:
        """Get a line of user input.

        Uses prompt_toolkit (with slash autocomplete) when running in an
        interactive terminal; falls back to a plain Rich prompt otherwise.
        """
        if pt_session is not None:
            from prompt_toolkit.formatted_text import HTML
            prompt_text = HTML("<ansicyan><b>❯</b></ansicyan> ")
            return await pt_session.prompt_async(prompt_text)
        # Non-interactive fallback
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: console.input("[bold cyan]❯[/bold cyan] ")
        )

    # ── Main UI ────────────────────────────────────────────────────────
    _render_banner()
    console.print()
    if pt_session:
        hint = "[dim]  Type a message to chat  ·  type [accent]/[/accent] for autocomplete  ·  [accent]/exit[/accent] to quit[/dim]"
    else:
        hint = "[dim]  Type a message to chat  ·  [accent]/help[/accent] for commands  ·  [accent]/exit[/accent] to quit[/dim]"
    console.print(hint)
    console.print()

    # Connection animation
    console.print("[dim]  Connecting...[/dim]", end="")

    try:
        ws = await websockets.connect(server_url)
    except ConnectionRefusedError:
        console.print(f"\r[error]  ✗ Could not connect to {server_url}[/error]")
        console.print("[dim]  Start the server first:[/dim]  steelclaw serve")
        sys.exit(1)
    except Exception as e:
        console.print(f"\r[error]  ✗ Connection error:[/error] {e}")
        sys.exit(1)

    console.print(f"\r[success]  ✓ Connected to {server_url}[/success]  ")
    console.print()

    try:
        while True:
            try:
                user_input = await _get_input()
            except EOFError:
                break

            stripped = user_input.strip()
            if not stripped:
                continue

            # ── Slash commands ──────────────────────────────────────────
            cmd = stripped.lower()
            cmd_parts = stripped.split(maxsplit=1)
            cmd_name = cmd_parts[0].lower()

            if cmd in ("/quit", "/exit"):
                console.print()
                console.print("[dim]  Goodbye![/dim]")
                break

            if cmd == "/clear":
                messages.clear()
                console.clear()
                _render_banner()
                console.print("[dim]  Chat cleared.[/dim]\n")
                continue

            if cmd == "/help":
                console.print(_render_help())
                continue

            if cmd == "/status":
                console.print(await _render_status(server_url, user_id, True))
                continue

            if cmd == "/stats":
                console.print(_render_stats())
                continue

            if cmd == "/history":
                if not messages:
                    console.print("[dim]  No messages yet.[/dim]")
                else:
                    for m in messages:
                        console.print(_render_message(m["role"], m["content"], m.get("time", "")))
                continue

            if cmd == "/compact":
                if not messages:
                    console.print("[dim]  No messages yet.[/dim]")
                else:
                    recent = messages[-20:]  # last 10 exchanges (20 messages = 10 user+assistant pairs)
                    console.print(f"[dim]  Showing last {len(recent)} messages[/dim]\n")
                    for m in recent:
                        role_tag = "[cyan]You[/]" if m["role"] == "user" else "[green]SC [/]"
                        preview = m["content"][:120].replace("\n", " ")
                        if len(m["content"]) > 120:
                            preview += "…"
                        ts = m.get("time", "")
                        console.print(f"  [dim]{ts}[/] {role_tag}  {preview}")
                continue

            if cmd == "/model":
                # Fetch live LLM config from the server without blocking the event loop
                _http_base = _ws_to_http_base(server_url)
                try:
                    import httpx as _httpx
                    async with _httpx.AsyncClient() as _client:
                        _resp = await _client.get(f"{_http_base}/api/config/llm", timeout=3.0)
                    if _resp.status_code == 200:
                        _llm = _resp.json().get("llm", {})
                        _tbl = Table(show_header=False, box=None, padding=(0, 2))
                        _tbl.add_column(style="dim", min_width=18)
                        _tbl.add_column()
                        _tbl.add_row("Model", f"[bold accent]{_llm.get('default_model', '—')}[/]")
                        _tbl.add_row("Temperature", f"[dim]{_llm.get('temperature', '—')}[/]")
                        _tbl.add_row("Max tokens", f"[dim]{_llm.get('max_tokens', '—')}[/]")
                        _tbl.add_row("Context msgs", f"[dim]{_llm.get('max_context_messages', '—')}[/]")
                        _tbl.add_row("Streaming", f"[dim]{_llm.get('streaming', '—')}[/]")
                        console.print(Panel(
                            _tbl,
                            title="[accent] Model [/]",
                            border_style="blue",
                            box=box.ROUNDED,
                        ))
                    else:
                        console.print("[dim]  Could not retrieve model info (server returned non-200).[/dim]")
                except Exception:
                    console.print("[dim]  Model info unavailable — is the server running? Try /status[/dim]")
                continue

            if cmd == "/new":
                messages.clear()
                console.print("[dim]  New conversation started.[/dim]\n")
                continue

            if cmd == "/version":
                console.print(_render_version(server_url))
                continue

            if cmd == "/pricing":
                console.print(_render_pricing())
                continue

            if cmd_name == "/export":
                fname = cmd_parts[1] if len(cmd_parts) > 1 else f"steelclaw_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                try:
                    with open(fname, "w") as f:
                        f.write(f"# SteelClaw Chat Export\n\n")
                        for m in messages:
                            role = "You" if m["role"] == "user" else "SteelClaw"
                            f.write(f"**{role}** ({m.get('time', '')}):\n{m['content']}\n\n---\n\n")
                    console.print(f"[success]  ✓ Exported to {fname}[/success]")
                except Exception as e:
                    console.print(f"[error]  ✗ Export failed: {e}[/error]")
                continue

            if cmd_name == "/sudo":
                # Map /sudo sub-args to steelclaw security sudo-* commands
                sudo_parts = shlex.split(cmd_parts[1]) if len(cmd_parts) > 1 else []
                sub = sudo_parts[0].lower() if sudo_parts else ""

                if sub == "enable":
                    cli_cmd = ["steelclaw", "security", "sudo-enable", "true"]
                elif sub == "disable":
                    cli_cmd = ["steelclaw", "security", "sudo-enable", "false"]
                elif sub == "whitelist":
                    wl_action = sudo_parts[1] if len(sudo_parts) > 1 else "list"
                    cli_cmd = ["steelclaw", "security", "sudo-whitelist", wl_action]
                    if len(sudo_parts) > 2:
                        cli_cmd.append(sudo_parts[2])
                elif sub == "status" or sub == "show" or sub == "":
                    cli_cmd = ["steelclaw", "security", "show"]
                else:
                    console.print(
                        "[error]  Usage:[/error] [accent]/sudo[/accent] "
                        "[dim]enable | disable | whitelist [list|add|remove <pattern>] | status[/dim]"
                    )
                    continue

                console.print(f"[dim]  Running:[/dim] [accent]{' '.join(cli_cmd)}[/accent]\n")
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda c=cli_cmd: subprocess.run(c)
                )
                console.print()
                continue

            if cmd_name in _CLI_PASSTHROUGH:
                # Strip the leading "/" and forward all remaining args to the CLI.
                subcmd = cmd_name[1:]
                extra = shlex.split(cmd_parts[1]) if len(cmd_parts) > 1 else []
                cli_cmd = ["steelclaw", subcmd] + extra
                console.print(f"[dim]  Running:[/dim] [accent]{' '.join(cli_cmd)}[/accent]\n")
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda c=cli_cmd: subprocess.run(c)
                )
                console.print()
                continue

            if cmd.startswith("/"):
                console.print(f"[error]  Unknown command: {cmd_name}[/error]  Type [accent]/help[/accent] for commands.")
                continue

            # ── Send message ───────────────────────────────────────────
            now = datetime.now().strftime("%H:%M:%S")
            messages.append({"role": "user", "content": stripped, "time": now})
            msg_count += 1
            console.print()

            # Send with streaming enabled
            payload = json.dumps({
                "content": stripped,
                "user_id": user_id,
                "stream": True,
            })
            await ws.send(payload)

            # ── Stream response with live rendering ────────────────────
            response_text = ""
            frame_idx = 0
            response_started = False
            # Track active tool spinners: call_id → rich.status.Status
            active_tool_statuses: dict[str, object] = {}

            def _make_tool_status_text(tool_name: str, label: str | None, skill: str | None) -> str:
                # Delegation events are enriched by the orchestrator so tool_name
                # is already "delegate_to_{agent_name}"; surface these distinctly.
                # NOTE: plain text only — callers wrap this in Text(...) which
                # does not process Rich markup tags.
                if tool_name.startswith("delegate_to_"):
                    agent_id = tool_name[len("delegate_to_"):]
                    return f"◈ Delegating → {agent_id}"
                parts = [f"⚙ Running: {tool_name}"]
                if label:
                    parts.append(f"— {label}")
                if skill and skill != tool_name:
                    parts.append(f"({skill})")
                return "  " + " ".join(parts)

            with Live(
                Text(f"  {THINKING_FRAMES[0]} Thinking...", style="dim"),
                console=console,
                refresh_per_second=15,
                transient=True,
            ) as live:
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=180)
                    except asyncio.TimeoutError:
                        response_text = "[Timeout — no response after 180s]"
                        break

                    event = json.loads(raw)
                    etype = event.get("type", "")

                    if etype == "chunk":
                        response_started = True
                        response_text += event.get("content", "")
                        # Live-render the Markdown as it streams in
                        try:
                            rendered = Markdown(response_text)
                        except Exception:
                            rendered = Text(response_text)
                        from rich.console import Group
                        parts = [rendered]
                        # Show any still-active tool indicators below content
                        for (tn, lbl, sk) in active_tool_statuses.values():
                            frame_idx = (frame_idx + 1) % len(TOOL_FRAMES)
                            parts.append(Text(_make_tool_status_text(tn, lbl, sk), style="tool"))
                        live.update(Panel(
                            Group(*parts),
                            title="[assistant] SteelClaw [/assistant]",
                            title_align="left",
                            border_style="green",
                            box=box.ROUNDED,
                            padding=(0, 1),
                        ))

                    elif etype == "tool_start":
                        tool_name = event.get("name", "?")
                        call_id = event.get("id") or tool_name
                        label = event.get("label")
                        skill = event.get("skill")
                        active_tool_statuses[call_id] = (tool_name, label, skill)
                        frame_idx = (frame_idx + 1) % len(TOOL_FRAMES)
                        from rich.console import Group
                        parts = []
                        if response_text:
                            try:
                                parts.append(Markdown(response_text))
                            except Exception:
                                parts.append(Text(response_text))
                        for (tn, lbl, sk) in active_tool_statuses.values():
                            parts.append(Text(
                                f"\n  {TOOL_FRAMES[frame_idx]} {_make_tool_status_text(tn, lbl, sk)}",
                                style="tool",
                            ))
                        live.update(Panel(
                            Group(*parts) if len(parts) > 1 else (parts[0] if parts else Text("")),
                            title="[assistant] SteelClaw [/assistant]",
                            title_align="left",
                            border_style="green",
                            box=box.ROUNDED,
                            padding=(0, 1),
                        ))

                    elif etype == "tool_end":
                        tool_name = event.get("name", "?")
                        call_id = event.get("id") or tool_name
                        duration_ms = event.get("duration_ms")
                        active_tool_statuses.pop(call_id, None)
                        # Brief flash showing tool completed
                        dur_str = f" [{duration_ms}ms]" if duration_ms is not None else ""
                        # Show agent name for delegation completions
                        if tool_name.startswith("delegate_to_"):
                            agent_id = tool_name[len("delegate_to_"):]
                            done_label = f"◈ {agent_id} done"
                        else:
                            done_label = f"{tool_name} done"
                        done_line = Text(f"\n  ✓ {done_label}{dur_str}", style="success")
                        from rich.console import Group
                        parts = []
                        if response_text:
                            try:
                                parts.append(Markdown(response_text))
                            except Exception:
                                parts.append(Text(response_text))
                        parts.append(done_line)
                        # Still show remaining active tools
                        for (tn, lbl, sk) in active_tool_statuses.values():
                            frame_idx = (frame_idx + 1) % len(TOOL_FRAMES)
                            parts.append(Text(
                                f"\n  {TOOL_FRAMES[frame_idx]} {_make_tool_status_text(tn, lbl, sk)}",
                                style="tool",
                            ))
                        live.update(Panel(
                            Group(*parts) if len(parts) > 1 else (parts[0] if parts else Text("")),
                            title="[assistant] SteelClaw [/assistant]",
                            title_align="left",
                            border_style="green",
                            box=box.ROUNDED,
                            padding=(0, 1),
                        ))

                    elif etype == "done":
                        response_text = event.get("content", response_text)
                        break

                    elif etype == "error":
                        response_text = event.get("content", "An error occurred.")
                        break

                    elif not etype:
                        # Legacy non-streaming response
                        response_text = event.get("content", str(event))
                        break

                    # Update thinking animation when no content yet and no tools active
                    if not response_started and not active_tool_statuses:
                        frame_idx = (frame_idx + 1) % len(THINKING_FRAMES)
                        live.update(Text(
                            f"  {THINKING_FRAMES[frame_idx]} Thinking...",
                            style="dim",
                        ))

            # Show final rendered response
            resp_time = datetime.now().strftime("%H:%M:%S")
            messages.append({"role": "assistant", "content": response_text, "time": resp_time})
            msg_count += 1
            console.print(_render_message("assistant", response_text, resp_time))
            console.print()

    except websockets.ConnectionClosed:
        console.print("\n[error]  Connection lost.[/error]")
    finally:
        await ws.close()
