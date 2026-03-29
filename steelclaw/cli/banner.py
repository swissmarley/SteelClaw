"""CLI ASCII art banner for SteelClaw startup."""

from __future__ import annotations

BANNER = (
    "\033[96m"
    r"""
   ______          __  _______
  / __/ /____ ___ / / / ___/ /__ _    __
 _\ \/ __/ -_) -_) / / /__/ / _ `/ |/| /
/___/\__/\__/\__/_/  \___/_/\_,_/|__/|__/

    ╔═══════════════════════════════════╗
    ║  ⚙  Autonomous AI Agent Engine  ⚙  ║
    ╚═══════════════════════════════════╝
"""
    "\033[0m"
)


def print_banner() -> None:
    """Print the SteelClaw banner in cyan. Call before argparse runs."""
    print(BANNER)
