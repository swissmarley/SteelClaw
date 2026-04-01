"""CLI memory management — status/search/clear for the vector store."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

console = Console()


def handle_memory(args: argparse.Namespace) -> None:
    action = getattr(args, "memory_action", None)
    if action == "status":
        _memory_status()
    elif action == "search":
        _memory_search(args.query, args.limit)
    elif action == "clear":
        _memory_clear(user=getattr(args, "user", None), session=getattr(args, "session", None))
    else:
        _memory_status()


def _memory_status() -> None:
    from steelclaw.memory.vector_store import VectorStore
    from steelclaw.settings import Settings

    settings = Settings()
    store = VectorStore(settings.agents.memory)

    if not store.available:
        console.print("[yellow]Memory system is not available[/yellow]")
        console.print("Install ChromaDB: pip install steelclaw[memory]")
        return

    count = store.count()
    console.print(f"[green]Memory system active[/green]")
    console.print(f"  Stored memories: {count}")
    console.print(f"  Backend: ChromaDB")
    console.print(f"  Path: {settings.agents.memory.chromadb_path}")


def _memory_search(query: str, limit: int = 5) -> None:
    from steelclaw.memory.vector_store import VectorStore
    from steelclaw.settings import Settings

    settings = Settings()
    store = VectorStore(settings.agents.memory)

    if not store.available:
        console.print("[yellow]Memory system is not available[/yellow]")
        return

    results = store.query(query, n_results=limit)
    if not results:
        console.print("[dim]No matching memories found[/dim]")
        return

    table = Table(title=f"Memory Search: '{query}'")
    table.add_column("#", width=3)
    table.add_column("Content", max_width=80)
    table.add_column("Distance", width=10)

    for i, doc in enumerate(results, 1):
        content = doc["document"][:120].replace("\n", " ")
        distance = f"{doc['distance']:.3f}"
        table.add_row(str(i), content, distance)

    console.print(table)


def _memory_clear(user: str | None = None, session: str | None = None) -> None:
    from steelclaw.memory.vector_store import VectorStore
    from steelclaw.settings import Settings

    settings = Settings()
    store = VectorStore(settings.agents.memory)

    if not store.available:
        console.print("[yellow]Memory system is not available[/yellow]")
        return

    console.print("[yellow]This will permanently delete stored memories.[/yellow]")
    confirm = console.input("Type 'yes' to confirm: ")
    if confirm.lower() != "yes":
        console.print("[dim]Cancelled[/dim]")
        return

    store.clear()
    console.print("[green]Memory cleared[/green]")
