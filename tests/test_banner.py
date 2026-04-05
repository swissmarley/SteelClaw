"""Tests for the CLI banner module."""

from __future__ import annotations

import io
import os
import sys
from unittest import mock

import pytest

from steelclaw.cli.banner import (
    _use_color,
    _get_version,
    _print_static,
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
    assert "v" in out


def test_print_static_contains_tagline(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "Autonomous AI Agent Engine" in out


def test_print_static_contains_help_hint(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "--help" in out


def test_print_static_contains_box_frame(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "╔" in out
    assert "╗" in out
    assert "╚" in out
    assert "╝" in out


def test_print_static_no_escape_codes_when_no_color(capsys):
    _print_static(color=False)
    out = capsys.readouterr().out
    assert "\033[" not in out


def test_print_static_escape_codes_with_color(capsys):
    _print_static(color=True)
    out = capsys.readouterr().out
    assert "\033[" in out


# ---------------------------------------------------------------------------
# print_banner
# ---------------------------------------------------------------------------

def test_print_banner_outputs_banner(capsys, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    print_banner()
    out = capsys.readouterr().out
    assert "Autonomous AI Agent Engine" in out
    assert "--help" in out


def test_print_banner_no_color_on_non_tty(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdout", _FakeNonTTY())
    monkeypatch.delenv("NO_COLOR", raising=False)
    print_banner()
