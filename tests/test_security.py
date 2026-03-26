"""Tests for the security module — approvals, permissions, sandbox."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from steelclaw.security.approvals import ApprovalStore
from steelclaw.security.permissions import PermissionManager
from steelclaw.settings import SecuritySettings


@pytest.fixture()
def tmp_approvals(tmp_path):
    return str(tmp_path / "approvals.json")


def test_approval_store_empty(tmp_approvals):
    store = ApprovalStore(tmp_approvals)
    assert store.check("ls -la") is None
    assert store.list_rules() == []


def test_approval_store_add_and_check(tmp_approvals):
    store = ApprovalStore(tmp_approvals)
    store.add_rule("git *", permission="ignore", note="All git commands")

    assert store.check("git status") == "ignore"
    assert store.check("git push origin main") == "ignore"
    assert store.check("rm -rf /") is None


def test_approval_store_glob_patterns(tmp_approvals):
    store = ApprovalStore(tmp_approvals)
    store.add_rule("ls *", permission="ignore")
    store.add_rule("cat *.txt", permission="record")

    assert store.check("ls -la") == "ignore"
    assert store.check("cat readme.txt") == "record"
    assert store.check("cat readme.md") is None


def test_approval_store_persistence(tmp_approvals):
    store1 = ApprovalStore(tmp_approvals)
    store1.add_rule("echo *", permission="ignore")

    # Reload from file
    store2 = ApprovalStore(tmp_approvals)
    assert store2.check("echo hello") == "ignore"


def test_approval_store_remove(tmp_approvals):
    store = ApprovalStore(tmp_approvals)
    store.add_rule("git *", permission="ignore")
    assert store.remove_rule("git *") is True
    assert store.check("git status") is None
    assert store.remove_rule("nonexistent") is False


def test_approval_store_overwrite(tmp_approvals):
    store = ApprovalStore(tmp_approvals)
    store.add_rule("git *", permission="ignore")
    store.add_rule("git *", permission="ask")
    assert store.check("git status") == "ask"
    assert len(store.list_rules()) == 1


@pytest.mark.asyncio
async def test_permission_blocked_command(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        blocked_commands=["rm -rf /"],
    )
    pm = PermissionManager(settings)
    result = await pm.check_command("rm -rf /")
    assert not result.allowed
    assert result.tier == "blocked"


@pytest.mark.asyncio
async def test_permission_ignore_tier(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        default_permission="ignore",
    )
    pm = PermissionManager(settings)
    result = await pm.check_command("echo hello")
    assert result.allowed
    assert result.tier == "ignore"


@pytest.mark.asyncio
async def test_permission_record_tier(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        default_permission="record",
    )
    pm = PermissionManager(settings)
    result = await pm.check_command("echo hello")
    assert result.allowed
    assert result.tier == "record"


@pytest.mark.asyncio
async def test_permission_ask_with_callback(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        default_permission="ask",
    )
    pm = PermissionManager(settings)

    async def approve(cmd: str) -> bool:
        return True

    pm.set_approval_callback(approve)
    result = await pm.check_command("echo hello")
    assert result.allowed
    assert result.user_approved

    # Should be auto-approved next time (persisted)
    result2 = await pm.check_command("echo hello")
    assert result2.allowed
    assert result2.tier == "ignore"


@pytest.mark.asyncio
async def test_permission_ask_denied(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        default_permission="ask",
    )
    pm = PermissionManager(settings)

    async def deny(cmd: str) -> bool:
        return False

    pm.set_approval_callback(deny)
    result = await pm.check_command("echo hello")
    assert not result.allowed


@pytest.mark.asyncio
async def test_permission_ask_no_callback(tmp_approvals):
    settings = SecuritySettings(
        approvals_file=tmp_approvals,
        default_permission="ask",
    )
    pm = PermissionManager(settings)
    # No callback set — should deny
    result = await pm.check_command("echo hello")
    assert not result.allowed
