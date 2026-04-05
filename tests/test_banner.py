"""Tests for the CLI banner module."""

from __future__ import annotations

import io
import os
import sys
import time
from unittest import mock

import pytest

from steelclaw.cli.banner import (
    _use_animation,
    _use_color,
    _get_version,
    _print_static,
    _animate_typewriter,
    print_banner,
)


# ---------------------------------------------------------------------------
# Helper guards
# ---------------------------------------------------------------------------

class _FakeTTY(io.StringIO):
    """StringIO that claims to be a TTY."""

    def isatty(self) -> bool:
        return True


class _FakeNonTTY(io.StringIO):
    """StringIO that is NOT a TTY."""

    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# _use_color
# ---------------------------------------------------------------------------

def test_use_color_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    assert _use_color() is True


def test_use_color_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    assert _use_color() is False


def test_use_color_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeNonTTY())
    assert _use_color() is False


# ---------------------------------------------------------------------------
# _use_animation
# ---------------------------------------------------------------------------

def test_use_animation_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    assert _use_animation() is True


def test_use_animation_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    assert _use_animation() is False


def test_use_animation_ci(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    assert _use_animation() is False


def test_use_animation_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(sys, "stdout", _FakeNonTTY())
    assert _use_animation() is False


# ---------------------------------------------------------------------------
# _get_version
# ---------------------------------------------------------------------------

def test_get_version_returns_string():
    v = _get_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_get_version_fallback(monkeypatch):
    """If importlib.metadata fails, fall back gracefully."""
    import importlib.metadata as _meta

    monkeypatch.setattr(_meta, "version", mock.Mock(side_effect=Exception("nope")))
    # Also patch the steelclaw __version__ import path
    with mock.patch.dict("sys.modules", {"steelclaw": mock.MagicMock(__version__="9.9.9")}):
        v = _get_version()
    assert isinstance(v, str)


# ---------------------------------------------------------------------------
# _print_static
# ---------------------------------------------------------------------------

def test_print_static_contains_logo(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "SteelClaw" in out or "___" in out or "__/" in out


def test_print_static_contains_version(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "v" in out  # version string starts with 'v'


def test_print_static_contains_tagline(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "Autonomous AI Agent Engine" in out


def test_print_static_contains_help_hint(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "--help" in out


def test_print_static_no_escape_codes_when_no_color(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "\033[" not in out


def test_print_static_escape_codes_with_color(capsys):
    _print_static(color=True)
    out = capsys.readouterr().out
    assert "\033[" in out


# ---------------------------------------------------------------------------
# _animate_typewriter
# ---------------------------------------------------------------------------

def test_animate_typewriter_output(capsys, monkeypatch):
    # Speed up by patching time.sleep to a no-op
    monkeypatch.setattr(time, "sleep", lambda _: None)
    _animate_typewriter(color=False)
    out = capsys.readouterr().out
    assert "Autonomous AI Agent Engine" in out
    assert "--help" in out


def test_animate_typewriter_keyboard_interrupt_handled(capsys, monkeypatch):
    """KeyboardInterrupt mid-animation should be handled in print_banner."""
    call_count = 0

    def _raise_on_second(*_):
        nonlocal call_count
        call_count += 1
        if call_count > 5:
            raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", _raise_on_second)
    # Make stdout appear as a TTY so animation path is taken
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)

    # Should not raise — KeyboardInterrupt is caught and fallback shown
    print_banner(animated=True)


# ---------------------------------------------------------------------------
# print_banner
# ---------------------------------------------------------------------------

def test_print_banner_static_when_not_animated(capsys, monkeypatch):
    # Don't replace sys.stdout so capsys can capture; just disable animation
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    print_banner(animated=False)
    out = capsys.readouterr().out
    assert "Autonomous AI Agent Engine" in out


def test_print_banner_animated_false_skips_animation(capsys, monkeypatch):
    """When animated=False, no time.sleep calls should occur."""
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

    print_banner(animated=False)
    assert sleep_calls == [], "Static banner must not call time.sleep"


def test_print_banner_animated_true_on_tty(capsys, monkeypatch):
    """When animated=True on a TTY, time.sleep should be called."""
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

    print_banner(animated=True)
    assert len(sleep_calls) > 0, "Animated banner must call time.sleep"


def test_print_banner_no_animation_in_ci(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("NO_COLOR", raising=False)
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

    print_banner(animated=True)
    assert sleep_calls == [], "CI env should disable animation"


def test_print_banner_no_animation_with_no_color(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdout", _FakeTTY())
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("CI", raising=False)
    sleep_calls = []
    monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

    print_banner(animated=True)
    assert sleep_calls == [], "NO_COLOR should disable animation"
