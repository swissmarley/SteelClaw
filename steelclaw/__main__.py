"""Entry point: python -m steelclaw [serve|chat]"""

from __future__ import annotations

import argparse
import logging
import sys


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the SteelClaw API server."""
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


def cmd_chat(args: argparse.Namespace) -> None:
    """Connect to a running SteelClaw server and chat interactively."""
    from steelclaw.cli.chat import run_chat

    run_chat(server_url=args.server, user_id=args.user)


def cmd_setup(args: argparse.Namespace) -> None:
    """Run the interactive onboarding wizard."""
    from steelclaw.cli.setup import run_setup

    run_setup()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="steelclaw",
        description="SteelClaw — self-hosted personal AI assistant",
    )
    sub = parser.add_subparsers(dest="command")

    # steelclaw serve
    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--host", type=str, default=None, help="Bind host (default: from config)")
    serve_p.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")

    # steelclaw chat
    chat_p = sub.add_parser("chat", help="Interactive CLI chat with SteelClaw")
    chat_p.add_argument(
        "--server", type=str, default="ws://localhost:8000/gateway/ws",
        help="WebSocket URL of the SteelClaw server",
    )
    chat_p.add_argument("--user", type=str, default="cli-user", help="User ID for the session")

    # steelclaw setup
    sub.add_parser("setup", help="Interactive onboarding wizard")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "setup":
        cmd_setup(args)
    else:
        # Default: start the server (backwards compatible)
        args.host = None
        args.port = None
        cmd_serve(args)


if __name__ == "__main__":
    main()
