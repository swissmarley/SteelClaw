"""CLI ASCII art banner for SteelClaw startup."""

from __future__ import annotations

import os
import sys
import time

_LOGO_LINES = [
    r"   ______          __  _______",
    r"  / __/ /____ ___ / / / ___/ /__ _    __",
    r" _\ \/ __/ -_) -_) / / /__/ / _ `/ |/| /",
    r"/___/\__/\__/\__/_/  \___/_/\_,_/|__/|__/",
]

_TAGLINE_BOX = [
    "    ╔═══════════════════════════════════╗",
    "    ║  ⚙  Autonomous AI Agent Engine  ⚙  ║",
    "    ╚═══════════════════════════════════╝",
]


def _use_color() -> bool:
    """Return True if color output should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return True


def _use_animation() -> bool:
    """Return True if animation should be shown (TTY, not NO_COLOR, not CI)."""
    if not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CI"):
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

    print(cyan)
    for line in _LOGO_LINES:
        print(line)
    print()
    for line in _TAGLINE_BOX:
        print(line)
    print(reset, end="")
    print(f"{dim}  v{version}  |  Run `steelclaw --help` for usage{reset}")
    print()


def _animate_typewriter(color: bool = True) -> None:
    """Typewriter reveal: print each logo line character by character."""
    cyan = "\033[96m" if color else ""
    reset = "\033[0m" if color else ""
    dim = "\033[2m" if color else ""

    version = _get_version()

    # Total animation budget: ~1.5 s for logo lines, rest for tagline
    all_lines = _LOGO_LINES + [""] + _TAGLINE_BOX
    total_chars = sum(len(l) for l in all_lines)
    delay = 1.5 / max(total_chars, 1)

    print(cyan, end="", flush=True)
    for line in _LOGO_LINES:
        for ch in line:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(delay)
        sys.stdout.write("\n")
        sys.stdout.flush()

    print()

    for line in _TAGLINE_BOX:
        for ch in line:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(delay)
        sys.stdout.write("\n")
        sys.stdout.flush()

    print(reset, end="")
    print(f"{dim}  v{version}  |  Run `steelclaw --help` for usage{reset}")
    print()


def print_banner(animated: bool = True) -> None:
    """Print the SteelClaw startup banner.

    Parameters
    ----------
    animated:
        When *True* (default) a typewriter animation is shown in interactive
        TTY sessions.  Animations are automatically disabled when ``NO_COLOR``
        is set, when stdout is not a TTY, or when the ``CI`` variable is set.
        Pass *False* to always show the static logo (equivalent to
        ``--static-logo``).
    """
    color = _use_color()

    if animated and _use_animation():
        try:
            _animate_typewriter(color=color)
        except KeyboardInterrupt:
            # User pressed Ctrl-C to skip animation — fall back to static
            sys.stdout.write("\n")
            _print_static(color=color)
    else:
        _print_static(color=color)
