"""Tests for the interactive permission system."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from steelclaw.security.permission_models import (
    PermissionDecision,
    PermissionRequest,
    PermissionRequestStatus,
    PermissionResponse,
    ResolvedRequest,
)
from steelclaw.security.broadcaster import PermissionBroadcaster, get_broadcaster, set_broadcaster


class TestPermissionModels:
    """Tests for permission data models."""

    def test_permission_decision_enum(self):
        """Test PermissionDecision enum values."""
        assert PermissionDecision.APPROVE_ONCE.value == "approve_once"
        assert PermissionDecision.APPROVE_SESSION.value == "approve_session"
        assert PermissionDecision.DENY.value == "deny"

    def test_permission_request_status_enum(self):
        """Test PermissionRequestStatus enum values."""
        assert PermissionRequestStatus.PENDING.value == "pending"
        assert PermissionRequestStatus.APPROVED.value == "approved"
        assert PermissionRequestStatus.DENIED.value == "denied"
        assert PermissionRequestStatus.TIMEOUT.value == "timeout"
        assert PermissionRequestStatus.CANCELLED.value == "cancelled"

    def test_permission_request_create(self):
        """Test PermissionRequest factory method."""
        request = PermissionRequest.create(
            command="ls -la",
            tool_name="shell",
            session_id="test-session",
            platform="websocket",
            platform_chat_id="chat-123",
            timeout_seconds=300,
            skill_name="shell",
            context="List files",
        )

        assert request.command == "ls -la"
        assert request.tool_name == "shell"
        assert request.session_id == "test-session"
        assert request.platform == "websocket"
        assert request.platform_chat_id == "chat-123"
        assert request.timeout_seconds == 300
        assert request.skill_name == "shell"
        assert request.context == "List files"
        assert request.status == PermissionRequestStatus.PENDING
        assert isinstance(request.request_id, str)
        assert isinstance(request.created_at, datetime)

    def test_permission_request_to_dict(self):
        """Test PermissionRequest serialization."""
        request = PermissionRequest.create(
            command="echo test",
            tool_name="shell",
            session_id="session-123",
            platform="telegram",
            platform_chat_id="chat-456",
        )

        data = request.to_dict()
        assert data["command"] == "echo test"
        assert data["tool_name"] == "shell"
        assert data["session_id"] == "session-123"
        assert "request_id" in data
        assert "timeout_seconds" in data
        assert "options" in data
        assert "approve_once" in data["options"]
        assert "approve_session" in data["options"]
        assert "deny" in data["options"]

    def test_permission_response(self):
        """Test PermissionResponse creation and serialization."""
        response = PermissionResponse(
            request_id="req-123",
            decision=PermissionDecision.APPROVE_ONCE,
            user_id="user-456",
            platform="telegram",
        )

        assert response.request_id == "req-123"
        assert response.decision == PermissionDecision.APPROVE_ONCE
        assert response.user_id == "user-456"
        assert response.platform == "telegram"
        assert isinstance(response.responded_at, datetime)

        data = response.to_dict()
        assert data["request_id"] == "req-123"
        assert data["decision"] == "approve_once"
        assert data["user_id"] == "user-456"
        assert data["platform"] == "telegram"

    def test_resolved_request(self):
        """Test ResolvedRequest creation and serialization."""
        resolved = ResolvedRequest(
            request_id="req-123",
            decision=PermissionDecision.APPROVE_SESSION,
            resolved_by="telegram:user-456",
            original_command="ls -la",
        )

        assert resolved.request_id == "req-123"
        assert resolved.decision == PermissionDecision.APPROVE_SESSION
        assert resolved.resolved_by == "telegram:user-456"
        assert resolved.original_command == "ls -la"

        data = resolved.to_dict()
        assert data["request_id"] == "req-123"
        assert data["decision"] == "approve_session"
        assert data["resolved_by"] == "telegram:user-456"
        assert data["original_command"] == "ls -la"


class TestPermissionBroadcaster:
    """Tests for PermissionBroadcaster."""

    def test_broadcaster_init(self):
        """Test broadcaster initialization."""
        broadcaster = PermissionBroadcaster(timeout_seconds=300)
        assert broadcaster._timeout == 300
        assert broadcaster._pending_requests == {}
        assert broadcaster._pending_responses == {}
        assert broadcaster._resolved_requests == {}

    def test_set_ws_connections_getter(self):
        """Test setting WebSocket connections getter."""
        broadcaster = PermissionBroadcaster()
        connections = set()
        broadcaster.set_ws_connections_getter(lambda: connections)
        assert broadcaster._get_ws_connections is not None
        assert broadcaster._get_ws_connections() is connections

    def test_global_broadcaster(self):
        """Test global broadcaster instance management."""
        broadcaster = PermissionBroadcaster()
        set_broadcaster(broadcaster)
        assert get_broadcaster() is broadcaster

        # Clean up
        set_broadcaster(None)
        assert get_broadcaster() is None

    async def test_resolve_request_first_wins(self):
        """Test that first response wins in resolve_request."""
        broadcaster = PermissionBroadcaster()

        # Create a pending request
        request = PermissionRequest.create(
            command="test",
            tool_name="shell",
            session_id="session-1",
            platform="test",
            platform_chat_id="chat-1",
        )
        broadcaster._pending_requests[request.request_id] = request
        broadcaster._pending_responses[request.request_id] = asyncio.Event()

        # First response
        response1 = PermissionResponse(
            request_id=request.request_id,
            decision=PermissionDecision.APPROVE_ONCE,
            user_id="user-1",
            platform="test",
        )

        result1 = await broadcaster.resolve_request(response1)
        assert result1 is True  # First response wins

        # Second response (should be rejected)
        response2 = PermissionResponse(
            request_id=request.request_id,
            decision=PermissionDecision.DENY,
            user_id="user-2",
            platform="test",
        )

        result2 = await broadcaster.resolve_request(response2)
        assert result2 is False  # Already resolved

    def test_broadcast_request_to_dict_format(self):
        """Test that broadcast_request uses correct format."""
        broadcaster = PermissionBroadcaster()
        request = PermissionRequest.create(
            command="rm -rf /",
            tool_name="shell",
            session_id="session-1",
            platform="telegram",
            platform_chat_id="chat-123",
            timeout_seconds=60,
            context="Deleting files",
        )

        # Verify the request has all necessary fields
        data = request.to_dict()
        assert "request_id" in data
        assert "command" in data
        assert "tool_name" in data
        assert "timeout_seconds" in data
        assert "options" in data
        assert len(data["options"]) == 3


class TestPermissionManagerIntegration:
    """Tests for PermissionManager with broadcaster integration."""

    @pytest.fixture()
    def tmp_approvals(self, tmp_path):
        return str(tmp_path / "approvals.json")

    async def test_check_command_with_session_approval(self, tmp_approvals):
        """Test that session-scoped approvals work."""
        from steelclaw.security.permissions import PermissionManager
        from steelclaw.settings import SecuritySettings

        settings = SecuritySettings(
            approvals_file=tmp_approvals,
            default_permission="ask",
        )
        pm = PermissionManager(settings)

        # Initially no session approvals
        assert pm._session_approvals == {}

        # Add a session approval manually
        pm._session_approvals["session-1"] = {"ls -la"}

        # Check command with session_id
        result = await pm.check_command(
            command="ls -la",
            session_id="session-1",
            platform="test",
            platform_chat_id="chat-1",
        )

        assert result.allowed
        assert result.session_approved

    def test_clear_session(self, tmp_approvals):
        """Test clearing session approvals."""
        from steelclaw.security.permissions import PermissionManager
        from steelclaw.settings import SecuritySettings

        settings = SecuritySettings(approvals_file=tmp_approvals)
        pm = PermissionManager(settings)

        # Add session approvals
        pm._session_approvals["session-1"] = {"cmd1", "cmd2"}
        pm._session_approvals["session-2"] = {"cmd3"}

        # Clear session-1
        pm.clear_session("session-1")

        assert "session-1" not in pm._session_approvals
        assert "session-2" in pm._session_approvals

    async def test_check_command_without_broadcaster(self, tmp_approvals):
        """Test that check_command works without broadcaster (legacy mode)."""
        from steelclaw.security.permissions import PermissionManager
        from steelclaw.settings import SecuritySettings

        settings = SecuritySettings(
            approvals_file=tmp_approvals,
            default_permission="ignore",
        )
        pm = PermissionManager(settings)

        result = await pm.check_command("echo test")
        assert result.allowed
        assert result.tier == "ignore"