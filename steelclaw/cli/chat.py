"""Interactive TUI chat client — streams responses in real time via WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
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

# ── Slash commands — single source of truth ────────────────────────────────

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help",    "Show available commands"),
    ("/exit",    "Exit the chat"),
    ("/quit",    "Exit the chat"),
    ("/clear",   "Clear conversation history"),
    ("/status",  "Connection and session info"),
    ("/history", "Show conversation history"),
    ("/compact", "Show history (compact, last 10)"),
    ("/model",   "Show current model info"),
    ("/stats",   "Show session statistics"),
    ("/new",     "Start a new conversation"),
    ("/export",  "Export chat to file"),
]


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
        tbl = Table(show_header=True, box=box.SIMPLE_HEAVY, padding=(0, 2))
        tbl.add_column("Command", style="accent", min_width=20)
        tbl.add_column("Description", style="dim")
        for cmd, desc in SLASH_COMMANDS:
            tbl.add_row(cmd, desc)
        tbl.add_row("Ctrl+C", "Exit immediately")
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

    def _render_status(url: str, uid: str, connected: bool) -> Panel:
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="dim", min_width=14)
        tbl.add_column()
        tbl.add_row("Server", f"[accent]{url}[/]")
        tbl.add_row("User", f"[accent]{uid}[/]")
        status_str = "[success]● Connected[/]" if connected else "[error]● Disconnected[/]"
        tbl.add_row("Status", status_str)
        tbl.add_row("Mode", "[accent]Streaming[/]")
        uptime = int(time.time() - start_time)
        mins, secs = divmod(uptime, 60)
        tbl.add_row("Uptime", f"[dim]{mins}m {secs}s[/]")
        tbl.add_row("Messages", f"[dim]{msg_count}[/]")
        return Panel(tbl, title="[accent] Status [/]", border_style="blue", box=box.ROUNDED)

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
        return await asyncio.get_event_loop().run_in_executor(
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
                console.print(_render_status(server_url, user_id, True))
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
                    recent = messages[-20:]  # last 10 exchanges
                    for m in recent:
                        role_tag = "[cyan]You[/]" if m["role"] == "user" else "[green]SC[/]"
                        preview = m["content"][:120].replace("\n", " ")
                        ts = m.get("time", "")
                        console.print(f"  [dim]{ts}[/] {role_tag}: {preview}")
                continue

            if cmd == "/model":
                console.print("[dim]  Model info is determined server-side. Check /status on the web UI.[/dim]")
                continue

            if cmd == "/new":
                messages.clear()
                console.print("[dim]  New conversation started.[/dim]\n")
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
            tool_active = False
            response_started = False

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
                        tool_active = False
                        response_text += event.get("content", "")
                        # Live-render the Markdown as it streams in
                        try:
                            rendered = Markdown(response_text)
                        except Exception:
                            rendered = Text(response_text)
                        live.update(Panel(
                            rendered,
                            title="[assistant] SteelClaw [/assistant]",
                            title_align="left",
                            border_style="green",
                            box=box.ROUNDED,
                            padding=(0, 1),
                        ))

                    elif etype == "tool_start":
                        tool_active = True
                        tool_name = event.get("name", "?")
                        frame_idx = (frame_idx + 1) % len(TOOL_FRAMES)
                        indicator = Text()
                        if response_text:
                            try:
                                indicator = Markdown(response_text)
                            except Exception:
                                indicator = Text(response_text)
                        status_line = Text(f"\n  {TOOL_FRAMES[frame_idx]} Using {tool_name}...", style="tool")
                        from rich.console import Group
                        live.update(Panel(
                            Group(indicator, status_line),
                            title="[assistant] SteelClaw [/assistant]",
                            title_align="left",
                            border_style="green",
                            box=box.ROUNDED,
                            padding=(0, 1),
                        ))

                    elif etype == "tool_end":
                        tool_active = False
                        tool_name = event.get("name", "?")
                        # Brief flash showing tool completed
                        if response_text:
                            try:
                                rendered = Markdown(response_text)
                            except Exception:
                                rendered = Text(response_text)
                            done_line = Text(f"\n  ✓ {tool_name} done", style="success")
                            from rich.console import Group
                            live.update(Panel(
                                Group(rendered, done_line),
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

                    # Update thinking animation when no content yet
                    if not response_started and not tool_active:
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
