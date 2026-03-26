"""Interactive TUI chat client using Rich — connects to SteelClaw server via WebSocket."""

from __future__ import annotations

import asyncio
import json
import sys
import os
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

    theme = Theme({
        "user": "bold cyan",
        "assistant": "bold green",
        "system": "bold yellow",
        "dim": "dim white",
        "error": "bold red",
        "accent": "bold blue",
    })
    console = Console(theme=theme)
    messages: list[dict] = []

    def _render_banner() -> Panel:
        banner_text = Text()
        banner_text.append("  ____  _             _  ____ _\n", style="bold blue")
        banner_text.append(" / ___|| |_ ___  ___| |/ ___| | __ ___      __\n", style="bold blue")
        banner_text.append(" \\___ \\| __/ _ \\/ _ \\ | |   | |/ _` \\ \\ /\\ / /\n", style="bold blue")
        banner_text.append("  ___) | ||  __/  __/ | |___| | (_| |\\ V  V /\n", style="bold blue")
        banner_text.append(" |____/ \\__\\___|\\___|_|\\____|_|\\__,_| \\_/\\_/\n", style="bold blue")
        return Panel(
            banner_text,
            border_style="blue",
            box=box.DOUBLE,
            padding=(0, 1),
        )

    def _render_help() -> Panel:
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="accent")
        tbl.add_column(style="dim")
        tbl.add_row("/quit, /exit", "Exit the chat")
        tbl.add_row("/clear", "Clear message history")
        tbl.add_row("/help", "Show this help")
        tbl.add_row("/status", "Connection info")
        tbl.add_row("/history", "Show conversation history")
        tbl.add_row("Shift+Enter", "Multiline input (paste)")
        return Panel(tbl, title="[accent]Commands[/]", border_style="dim", box=box.ROUNDED)

    def _render_message(role: str, content: str, ts: str = "") -> Panel:
        if role == "user":
            label = "[user]You[/user]"
            border = "cyan"
        else:
            label = "[assistant]SteelClaw[/assistant]"
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
        tbl.add_column(style="dim")
        tbl.add_column()
        tbl.add_row("Server", url)
        tbl.add_row("User", uid)
        status_str = "[green]Connected[/]" if connected else "[red]Disconnected[/]"
        tbl.add_row("Status", status_str)
        return Panel(tbl, title="[accent]Status[/]", border_style="dim", box=box.ROUNDED)

    console.print(_render_banner())
    console.print(
        "[dim]Type [accent]/help[/accent] for commands  |  "
        "Press [accent]Enter[/accent] to send  |  "
        "[accent]Ctrl+C[/accent] to quit[/dim]\n"
    )
    console.print(f"[dim]Connecting to {server_url} ...[/dim]")

    try:
        async with websockets.connect(server_url) as ws:
            console.print("[green]Connected![/green]\n")

            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: console.input("[user]you>[/user] ")
                    )
                except EOFError:
                    break

                stripped = user_input.strip()
                if not stripped:
                    continue

                # Local commands
                cmd = stripped.lower()
                if cmd in ("/quit", "/exit"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                if cmd == "/clear":
                    messages.clear()
                    console.clear()
                    console.print(_render_banner())
                    console.print("[dim]Chat cleared.[/dim]\n")
                    continue
                if cmd == "/help":
                    console.print(_render_help())
                    continue
                if cmd == "/status":
                    console.print(_render_status(server_url, user_id, True))
                    continue
                if cmd == "/history":
                    if not messages:
                        console.print("[dim]No messages yet.[/dim]")
                    else:
                        for m in messages:
                            console.print(_render_message(m["role"], m["content"], m.get("time", "")))
                    continue

                # Send message
                now = datetime.now().strftime("%H:%M:%S")
                messages.append({"role": "user", "content": stripped, "time": now})
                console.print(_render_message("user", stripped, now))

                payload = json.dumps({"content": stripped, "user_id": user_id})
                await ws.send(payload)

                # Show thinking indicator
                with console.status("[dim]SteelClaw is thinking...[/dim]", spinner="dots"):
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=180)
                        data = json.loads(raw)
                        response = data.get("content", str(data))
                    except asyncio.TimeoutError:
                        response = "[Timeout — no response after 180s]"

                resp_time = datetime.now().strftime("%H:%M:%S")
                messages.append({"role": "assistant", "content": response, "time": resp_time})
                console.print(_render_message("assistant", response, resp_time))
                console.print()

    except ConnectionRefusedError:
        console.print(f"\n[error]Could not connect to {server_url}[/error]")
        console.print("[dim]Start the server first:[/dim]  steelclaw serve")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[error]Connection error:[/error] {e}")
        sys.exit(1)
