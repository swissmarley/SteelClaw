"""Tests for the sandboxed command execution."""

from __future__ import annotations

import pytest

from steelclaw.security.sandbox import execute_command


@pytest.mark.asyncio
async def test_basic_command():
    result = await execute_command("echo hello", check_permissions=False)
    assert "hello" in result


@pytest.mark.asyncio
async def test_command_timeout():
    result = await execute_command("sleep 10", timeout=1, check_permissions=False)
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_command_with_stderr():
    result = await execute_command("ls /nonexistent_path_xyz", check_permissions=False)
    assert "STDERR" in result or "No such file" in result or "Exit code" in result


@pytest.mark.asyncio
async def test_working_directory():
    result = await execute_command("pwd", working_directory="/tmp", check_permissions=False)
    # macOS resolves /tmp to /private/tmp
    assert "tmp" in result.lower()


@pytest.mark.asyncio
async def test_invalid_working_directory():
    result = await execute_command(
        "echo test",
        working_directory="/nonexistent_dir_xyz",
        check_permissions=False,
    )
    assert "does not exist" in result
