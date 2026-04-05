"""CLI ASCII art banner for SteelClaw startup."""

from __future__ import annotations

import os
import sys

_LOGO_LINES = [
    r" /$$$$$$$   /$$                         /$$  /$$$$$$  /$$                        ",
    r"/ $$__  $$ | $$                        | $$ /$$__  $$| $$                        ",
    r"| $$  \__//$$$$$$    /$$$$$$   /$$$$$$ | $$| $$  \__/| $$  /$$$$$$  /$$  /$$  /$$",
    r"|  $$$$$$|_  $$_/   /$$__  $$ /$$__  $$| $$| $$      | $$ |____  $$| $$ | $$ | $$",
    r" \____  $$ | $$    | $$$$$$$$| $$$$$$$$| $$| $$      | $$  /$$$$$$$| $$ | $$ | $$",
    r" /$$  \ $$ | $$ /$$| $$_____/| $$_____/| $$| $$    $$| $$ /$$__  $$| $$ | $$ | $$",
    r"|  $$$$$$/ |  $$$$/|  $$$$$$$|  $$$$$$$| $$|  $$$$$$/| $$|  $$$$$$$|  $$$$$/$$$$/",
    r" \______/   \___/   \_______/ \_______/|__/ \______/ |__/ \_______/ \_____/\___/ ",
]

_TAGLINE = "⚙  Autonomous AI Agent Engine  ⚙"

# Inner box width: widest logo line + 4 chars padding (2 each side)
_BOX_W = max(len(line) for line in _LOGO_LINES) + 4


def _use_color() -> bool:
    """Return True if color output should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return True


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("steelclaw")
    except Exception:
        pass
    try:
        from steelclaw import __version__
        return __version__
    except Exception:
        return "0.3.0"


def _print_static(color: bool = True) -> None:
    """Print the full static banner."""
    cyan = "\033[96m" if color else ""
    reset = "\033[0m" if color else ""
    dim = "\033[2m" if color else ""

    version = _get_version()

    top = "╔" + "═" * _BOX_W + "╗"
    sep = "╠" + "═" * _BOX_W + "╣"
    bot = "╚" + "═" * _BOX_W + "╝"

    def row(text: str) -> str:
        return "║  " + text.ljust(_BOX_W - 2) + "║"

    tagline_row = "║" + _TAGLINE.center(_BOX_W) + "║"

    print(cyan + top)
    for line in _LOGO_LINES:
        print(row(line))
    print(sep)
    print(tagline_row)
    print(bot + reset)
    print(f"{dim}  v{version}  |  Run `steelclaw --help` for usage{reset}")
    print()


def print_banner() -> None:
    """Print the SteelClaw startup banner."""
    _print_static(color=_use_color())
