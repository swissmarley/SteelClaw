"""Entry point: python -m steelclaw [command]"""

from __future__ import annotations

import argparse
import logging
import sys


def _show_banner() -> None:
    """Show ASCII banner unless --no-banner is passed."""
    if "--no-banner" in sys.argv:
        return
    from steelclaw.cli.banner import print_banner
    static_only = "--static-logo" in sys.argv
    print_banner(animated=not static_only)


# ── Server commands ─────────────────────────────────────────────────────────


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the SteelClaw API server in foreground."""
    import uvicorn

    from steelclaw.app import create_app
    from steelclaw.settings import Settings

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    settings = Settings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=args.host or settings.server.host,
        port=args.port or settings.server.port,
        log_level=settings.server.log_level,
    )


def cmd_start(args: argparse.Namespace) -> None:
    """Start SteelClaw as a background daemon."""
    from steelclaw.cli.daemon import start_daemon
    start_daemon(host=args.host, port=args.port)


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the background daemon."""
    from steelclaw.cli.daemon import stop_daemon
    stop_daemon()


def cmd_restart(args: argparse.Namespace) -> None:
    """Restart the background daemon."""
    from steelclaw.cli.daemon import restart_daemon
    restart_daemon(host=args.host, port=args.port)


def cmd_status(args: argparse.Namespace) -> None:
    """Show daemon status."""
    from steelclaw.cli.daemon import show_status
    show_status()


# ── Chat ────────────────────────────────────────────────────────────────────


def cmd_chat(args: argparse.Namespace) -> None:
    """Connect to a running SteelClaw server and chat interactively."""
    from steelclaw.cli.chat import run_chat
    run_chat(server_url=args.server, user_id=args.user)


# ── Setup / Onboarding ─────────────────────────────────────────────────────


def cmd_setup(args: argparse.Namespace) -> None:
    """Run the interactive onboarding wizard."""
    from steelclaw.cli.setup import run_setup
    run_setup(reset=getattr(args, "reset", False))


# ── Sessions ────────────────────────────────────────────────────────────────


def cmd_sessions(args: argparse.Namespace) -> None:
    """Manage sessions."""
    from steelclaw.cli.sessions import handle_sessions
    handle_sessions(args)


# ── Memory ──────────────────────────────────────────────────────────────────


def cmd_memory(args: argparse.Namespace) -> None:
    """Manage persistent memory."""
    from steelclaw.cli.memory import handle_memory
    handle_memory(args)


# ── Agents ──────────────────────────────────────────────────────────────────


def cmd_agents(args: argparse.Namespace) -> None:
    """Manage agents."""
    from steelclaw.cli.agents import handle_agents
    handle_agents(args)


# ── Skills ──────────────────────────────────────────────────────────────────


def cmd_skills(args: argparse.Namespace) -> None:
    """Manage skills."""
    from steelclaw.cli.skills_cmd import handle_skills
    handle_skills(args)


# ── Logs ────────────────────────────────────────────────────────────────────


def cmd_logs(args: argparse.Namespace) -> None:
    """View daemon logs."""
    from steelclaw.cli.logs import show_logs
    show_logs(
        follow=args.follow,
        lines=args.lines,
        gateway=args.gateway,
        app=args.app,
    )


# ── Migrate ─────────────────────────────────────────────────────────────────


def cmd_migrate(args: argparse.Namespace) -> None:
    """Run database migrations."""
    import asyncio
    from steelclaw.settings import Settings

    settings = Settings()

    async def _run():
        from steelclaw.db.engine import dispose_engine, init_engine, run_migrations
        init_engine(settings.database.url, echo=settings.database.echo)
        await run_migrations()
        await dispose_engine()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(_run())
    print("Migrations applied successfully.")


# ── Gateway ─────────────────────────────────────────────────────────────────


def cmd_gateway(args: argparse.Namespace) -> None:
    """Manage gateway connectors."""
    from steelclaw.cli.gateway_cmd import handle_gateway
    handle_gateway(args)


def cmd_connectors(args: argparse.Namespace) -> None:
    """Manage gateway connectors (list, configure, enable, disable, status)."""
    from steelclaw.cli.connectors_cmd import handle_connectors
    handle_connectors(args)


# ── App ─────────────────────────────────────────────────────────────────────


def cmd_app_mgmt(args: argparse.Namespace) -> None:
    """Manage app components."""
    from steelclaw.cli.app_cmd import handle_app
    handle_app(args)


# ── Persona ─────────────────────────────────────────────────────────────────


def cmd_persona(args: argparse.Namespace) -> None:
    """Configure agent persona interactively."""
    from steelclaw.cli.persona import handle_persona
    handle_persona(args)


# ── Main parser ─────────────────────────────────────────────────────────────


def main() -> None:
    _show_banner()

    parser = argparse.ArgumentParser(
        prog="steelclaw",
        description="SteelClaw — self-hosted personal AI assistant",
    )
    parser.add_argument("--no-banner", action="store_true", help="Suppress the startup banner")
    parser.add_argument("--static-logo", action="store_true", help="Show static logo without animation")
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_p = sub.add_parser("serve", help="Start the API server (foreground)")
    serve_p.add_argument("--host", type=str, default=None, help="Bind host")
    serve_p.add_argument("--port", type=int, default=None, help="Bind port")

    # start
    start_p = sub.add_parser("start", help="Start as background daemon")
    start_p.add_argument("--host", type=str, default=None, help="Bind host")
    start_p.add_argument("--port", type=int, default=None, help="Bind port")

    # stop
    sub.add_parser("stop", help="Stop the background daemon")

    # restart
    restart_p = sub.add_parser("restart", help="Restart the background daemon")
    restart_p.add_argument("--host", type=str, default=None, help="Bind host")
    restart_p.add_argument("--port", type=int, default=None, help="Bind port")

    # status
    sub.add_parser("status", help="Show daemon running status")

    # chat
    chat_p = sub.add_parser("chat", help="Interactive CLI chat with SteelClaw")
    chat_p.add_argument(
        "--server", type=str, default="ws://localhost:8000/gateway/ws",
        help="WebSocket URL of the SteelClaw server",
    )
    chat_p.add_argument("--user", type=str, default="cli-user", help="User ID")

    # setup / onboard
    setup_p = sub.add_parser("setup", help="Interactive onboarding wizard")
    setup_p.add_argument("--reset", action="store_true", help="Reset config and re-run onboarding")
    onboard_p = sub.add_parser("onboard", help="Interactive onboarding wizard (alias for setup)")
    onboard_p.add_argument("--reset", action="store_true", help="Reset config and re-run onboarding")

    # sessions
    sessions_p = sub.add_parser("sessions", help="Manage sessions")
    sessions_sub = sessions_p.add_subparsers(dest="sessions_action")
    sessions_sub.add_parser("list", help="List active sessions")
    sessions_reset_p = sessions_sub.add_parser("reset", help="Reset a session (clear messages)")
    sessions_reset_p.add_argument("session_id", help="Session ID to reset")
    sessions_delete_p = sessions_sub.add_parser("delete", help="Delete a session")
    sessions_delete_p.add_argument("session_id", help="Session ID to delete")

    # memory
    memory_p = sub.add_parser("memory", help="Manage persistent memory")
    memory_sub = memory_p.add_subparsers(dest="memory_action")
    memory_sub.add_parser("status", help="Show memory system status")
    memory_search_p = memory_sub.add_parser("search", help="Search memories semantically")
    memory_search_p.add_argument("query", help="Search query")
    memory_search_p.add_argument("--limit", type=int, default=5, help="Number of results")
    memory_clear_p = memory_sub.add_parser("clear", help="Clear memory store")
    memory_clear_p.add_argument("--user", type=str, default=None, help="Clear for specific user")
    memory_clear_p.add_argument("--session", type=str, default=None, help="Clear for specific session")

    # agents
    agents_p = sub.add_parser("agents", help="Manage agents")
    agents_sub = agents_p.add_subparsers(dest="agents_action")
    agents_sub.add_parser("list", help="List all agents")
    agents_add_p = agents_sub.add_parser("add", help="Create a new agent")
    agents_add_p.add_argument("--name", required=True, help="Agent name")
    agents_add_p.add_argument("--model", default=None, help="Model override")
    agents_add_p.add_argument("--persona", default=None, help="Persona config file (JSON)")
    agents_delete_p = agents_sub.add_parser("delete", help="Delete an agent")
    agents_delete_p.add_argument("name", help="Agent name to delete")
    agents_sub.add_parser("status", help="Show agent status")

    # skills
    skills_p = sub.add_parser("skills", help="Manage skills")
    skills_sub = skills_p.add_subparsers(dest="skills_action")
    skills_sub.add_parser("list", help="List installed skills")
    skills_install_p = skills_sub.add_parser("install", help="Install a skill")
    skills_install_p.add_argument("path", help="Path to skill directory")
    skills_enable_p = skills_sub.add_parser("enable", help="Enable a skill")
    skills_enable_p.add_argument("name", help="Skill name")
    skills_disable_p = skills_sub.add_parser("disable", help="Disable a skill")
    skills_disable_p.add_argument("name", help="Skill name")
    skills_configure_p = skills_sub.add_parser(
        "configure",
        help="Configure skill credentials (interactive menu if no name given)",
    )
    skills_configure_p.add_argument(
        "name", nargs="?", default=None, help="Skill name (omit for interactive menu)"
    )

    # logs
    logs_p = sub.add_parser("logs", help="View daemon logs")
    logs_p.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    logs_p.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show")
    logs_p.add_argument("--gateway", action="store_true", help="Show gateway logs only")
    logs_p.add_argument("--app", action="store_true", help="Show app logs only")

    # migrate
    sub.add_parser("migrate", help="Run database migrations")

    # gateway
    gateway_p = sub.add_parser("gateway", help="Manage gateway connectors")
    gateway_sub = gateway_p.add_subparsers(dest="gateway_action")
    for action in ("start", "stop", "restart", "reset", "kill"):
        gw_action_p = gateway_sub.add_parser(action, help=f"{action.title()} a connector")
        gw_action_p.add_argument("connector", nargs="?", default=None, help="Connector name")

    # connectors
    connectors_p = sub.add_parser("connectors", help="Manage gateway connectors")
    connectors_sub = connectors_p.add_subparsers(dest="connectors_action")
    connectors_sub.add_parser("list", help="List all connectors with status")
    connectors_configure_p = connectors_sub.add_parser(
        "configure",
        help="Configure connector credentials (interactive if no name given)",
    )
    connectors_configure_p.add_argument(
        "name", nargs="?", default=None, help="Connector name (omit for interactive menu)"
    )
    connectors_enable_p = connectors_sub.add_parser("enable", help="Enable and start a connector")
    connectors_enable_p.add_argument("name", help="Connector name")
    connectors_disable_p = connectors_sub.add_parser("disable", help="Stop and disable a connector")
    connectors_disable_p.add_argument("name", help="Connector name")
    connectors_status_p = connectors_sub.add_parser("status", help="Show connector status and config")
    connectors_status_p.add_argument("name", help="Connector name")

    # app
    app_p = sub.add_parser("app", help="Manage app components")
    app_sub = app_p.add_subparsers(dest="app_action")
    for action in ("start", "stop", "restart", "reset", "kill"):
        app_sub.add_parser(action, help=f"{action.title()} the app")

    # persona
    sub.add_parser("persona", help="Configure agent persona interactively")

    args = parser.parse_args()

    commands = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "chat": cmd_chat,
        "setup": cmd_setup,
        "onboard": cmd_setup,
        "sessions": cmd_sessions,
        "memory": cmd_memory,
        "agents": cmd_agents,
        "skills": cmd_skills,
        "logs": cmd_logs,
        "migrate": cmd_migrate,
        "gateway": cmd_gateway,
        "connectors": cmd_connectors,
        "app": cmd_app_mgmt,
        "persona": cmd_persona,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        # Default: start the server (backwards compatible)
        args.host = None
        args.port = None
        cmd_serve(args)


if __name__ == "__main__":
    main()
