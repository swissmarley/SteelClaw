"""CLI memory management — status/search/clear for the vector store."""

from __future__ import annotations

import argparse
import asyncio
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
    elif action == "start":
        asyncio.run(_memory_start())
    elif action == "stop":
        asyncio.run(_memory_stop())
    elif action == "backend":
        _memory_backend()
    elif action == "migrate":
        asyncio.run(_memory_migrate(
            from_backend=getattr(args, "from_backend", "chromadb"),
            to_backend=getattr(args, "to_backend", "openviking"),
        ))
    elif action == "experiences":
        asyncio.run(_memory_experiences(
            query=getattr(args, "query", None),
            limit=getattr(args, "limit", 10),
        ))
    else:
        _memory_status()


def _get_store(settings):
    """Factory: returns the configured memory backend."""
    memory_settings = settings.agents.memory
    if memory_settings.backend == "openviking":
        from steelclaw.memory.viking_store import VikingStore
        return VikingStore(memory_settings)
    from steelclaw.memory.vector_store import VectorStore
    return VectorStore(memory_settings)


def _memory_status() -> None:
    from steelclaw.settings import Settings

    settings = Settings()
    memory_settings = settings.agents.memory
    store = _get_store(settings)

    console.print(f"[green]Memory system status[/green]")
    console.print(f"  Backend: {memory_settings.backend}")

    if memory_settings.backend == "openviking":
        console.print(f"  Server URL: {memory_settings.openviking_server_url}")
        console.print(f"  Workspace: {memory_settings.openviking_workspace}")
        console.print(f"  Context tier: {memory_settings.openviking_context_tier}")
        console.print(f"  Auto-start: {memory_settings.openviking_auto_start}")

        # Check server status
        import httpx
        try:
            resp = httpx.get(f"{memory_settings.openviking_server_url.rstrip('/')}/health", timeout=2.0)
            if resp.status_code == 200:
                console.print(f"  Server status: [green]running[/green]")
            else:
                console.print(f"  Server status: [yellow]unhealthy (status {resp.status_code})[/yellow]")
        except Exception as e:
            console.print(f"  Server status: [red]not reachable[/red] ({e})")
    else:
        console.print(f"  Path: {memory_settings.chromadb_path}")
        console.print(f"  Collection: {memory_settings.collection_name}")

    if store.available:
        count = store.count()
        console.print(f"  Stored memories: {count}")
    else:
        from steelclaw.memory.viking_store import _openviking_available as _ov_avail
        if memory_settings.backend == "openviking":
            if not _ov_avail:
                console.print(f"  [red]openviking package not installed[/red]")
                console.print("  Fix: pip install steelclaw[openviking]")
            else:
                console.print(f"  [yellow]Server not connected[/yellow] — start with: steelclaw start")
        else:
            console.print(f"  [yellow]Memory backend not available[/yellow]")
            console.print("  Install with: pip install steelclaw[memory]")


def _memory_backend() -> None:
    """Show current memory backend configuration."""
    from steelclaw.settings import Settings

    settings = Settings()
    memory_settings = settings.agents.memory

    console.print(f"[green]Current memory backend:[/green] {memory_settings.backend}")
    if memory_settings.backend == "openviking":
        console.print(f"  Server: {memory_settings.openviking_server_url}")
        console.print(f"  Workspace: {memory_settings.openviking_workspace}")
    else:
        console.print(f"  Path: {memory_settings.chromadb_path}")
        console.print(f"  Collection: {memory_settings.collection_name}")

    console.print("\n[dim]To change backend, edit config.json:[/dim]")
    console.print('[dim]  {"agents": {"memory": {"backend": "openviking"}}}[/dim]')


def _memory_search(query: str, limit: int = 5) -> None:
    from steelclaw.settings import Settings

    settings = Settings()
    store = _get_store(settings)

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
    from steelclaw.settings import Settings

    settings = Settings()
    store = _get_store(settings)

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


async def _memory_start() -> None:
    """Start the OpenViking server manually."""
    from steelclaw.memory.openviking_manager import OpenVikingManager
    from steelclaw.settings import Settings

    settings = Settings()
    memory_settings = settings.agents.memory

    if memory_settings.backend != "openviking":
        console.print("[yellow]Current backend is not OpenViking[/yellow]")
        console.print("Change backend in config.json: {\"agents\": {\"memory\": {\"backend\": \"openviking\"}}}")
        return

    manager = OpenVikingManager(memory_settings)
    success = await manager.start()
    if success:
        console.print(f"[green]OpenViking server started on port {memory_settings.openviking_port}[/green]")
    else:
        console.print("[red]Failed to start OpenViking server[/red]")
        console.print("Check logs for details or run: openviking-server --port 1933")


async def _memory_stop() -> None:
    """Stop the OpenViking server."""
    from steelclaw.memory.openviking_manager import OpenVikingManager
    from steelclaw.settings import Settings

    settings = Settings()
    memory_settings = settings.agents.memory

    if memory_settings.backend != "openviking":
        console.print("[yellow]Current backend is not OpenViking[/yellow]")
        return

    manager = OpenVikingManager(memory_settings)
    await manager.stop()
    console.print("[green]OpenViking server stopped[/green]")


async def _memory_migrate(from_backend: str, to_backend: str) -> None:
    """Migrate memories from one backend to another."""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    from steelclaw.settings import Settings

    settings = Settings()

    console.print(f"[blue]Migrating memories from {from_backend} to {to_backend}...[/blue]")

    # Get source store
    if from_backend == "openviking":
        from steelclaw.memory.viking_store import VikingStore
        source = VikingStore(settings.agents.memory)
    else:
        from steelclaw.memory.vector_store import VectorStore
        source = VectorStore(settings.agents.memory)

    # Temporarily switch backend for destination
    orig_backend = settings.agents.memory.backend
    settings.agents.memory.backend = to_backend

    if to_backend == "openviking":
        from steelclaw.memory.viking_store import VikingStore
        dest = VikingStore(settings.agents.memory)
    else:
        from steelclaw.memory.vector_store import VectorStore
        dest = VectorStore(settings.agents.memory)

    # Restore original backend
    settings.agents.memory.backend = orig_backend

    if not source.available:
        console.print(f"[red]Source backend ({from_backend}) is not available[/red]")
        return
    if not dest.available:
        console.print(f"[red]Destination backend ({to_backend}) is not available[/red]")
        return

    # Get all documents from source
    # Note: This is a simplified migration - real implementation would need
    # to handle pagination for large datasets
    console.print("[dim]Fetching documents from source...[/dim]")

    # We need to query all documents - use empty query to get everything
    all_docs = source.query("", n_results=10000)

    if not all_docs:
        console.print("[yellow]No documents to migrate[/yellow]")
        return

    console.print(f"[dim]Migrating {len(all_docs)} documents...[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Migrating", total=len(all_docs))

        for doc in all_docs:
            dest.add(
                text=doc["document"],
                metadata=doc.get("metadata"),
                doc_id=doc.get("id"),
            )
            progress.advance(task)

    # Commit if OpenViking destination
    if to_backend == "openviking" and hasattr(dest, "commit_session"):
        dest.commit_session()

    console.print(f"[green]Migration complete: {len(all_docs)} documents migrated[/green]")
    console.print(f"[dim]Update config.json to use {to_backend} as default backend[/dim]")


async def _memory_experiences(query: str | None = None, limit: int = 10) -> None:
    """List or search stored experience entries."""
    from steelclaw.settings import Settings
    from steelclaw.memory.retrieval import MemoryRetriever

    settings = Settings()
    store = _get_store(settings)

    if not store.available:
        console.print("[yellow]Memory system is not available[/yellow]")
        return

    retriever = MemoryRetriever(store)

    if query:
        # Search for matching experiences
        experiences = await retriever.retrieve_experiences(query=query, limit=limit)

        if not experiences:
            console.print(f"[dim]No matching experiences found for: {query}[/dim]")
            return

        table = Table(title=f"Experience Search: '{query}'")
        table.add_column("#", width=3)
        table.add_column("Task", max_width=50)
        table.add_column("Outcome", width=10)
        table.add_column("Tags", max_width=30)

        for i, (text, meta) in enumerate(experiences, 1):
            task = meta.get("task_summary", text[:50])
            outcome = meta.get("outcome", "unknown")
            tags = ", ".join(meta.get("tags") or [])[:30]
            table.add_row(str(i), task, outcome, tags)

        console.print(table)
    else:
        # List all experiences (using empty query to get all)
        experiences = await retriever.retrieve_experiences(query="", limit=limit)

        if not experiences:
            console.print("[dim]No stored experiences found[/dim]")
            console.print("[dim]Experiences are created when tasks complete successfully.[/dim]")
            return

        table = Table(title="Stored Experiences")
        table.add_column("#", width=3)
        table.add_column("Task", max_width=50)
        table.add_column("Outcome", width=10)
        table.add_column("Steps", width=6)

        for i, (text, meta) in enumerate(experiences, 1):
            task = meta.get("task_summary", text[:50])
            outcome = meta.get("outcome", "unknown")
            steps = str(meta.get("steps_count", "?"))
            table.add_row(str(i), task, outcome, steps)

        console.print(table)
        console.print(f"\n[dim]Use --query to search for specific experiences[/dim]")
