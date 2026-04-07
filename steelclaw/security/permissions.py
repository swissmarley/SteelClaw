"""Three-tier permission model for command execution.

Tiers:
  - "ask":    Prompt the user via WebSocket before executing.
  - "record": Log the action but allow execution.
  - "ignore": Auto-allow silently.

Extended capability permissions from ~/.steelclaw/permissions.yaml are checked
*before* the approval store, allowing category-level (network, packages, etc.)
blocking independent of individual command rules.

Interactive Permission System:
When a command needs approval (tier="ask"), the system broadcasts a permission
request to all connected channels (WebUI, CLI, Telegram, Discord, Slack).
Users can approve once, approve for session, or deny. First response wins.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Optional

from steelclaw.security.approvals import ApprovalStore
from steelclaw.security.permission_models import (
    PermissionDecision,
    PermissionRequest,
    PermissionRequestStatus,
)
from steelclaw.settings import SecuritySettings

logger = logging.getLogger("steelclaw.security.permissions")

# Callback type: async fn(command) -> bool (True = approved, False = denied)
# Deprecated: Use PermissionBroadcaster for interactive permissions
ApprovalCallback = Callable[[str], Coroutine[Any, Any, bool]]


class PermissionManager:
    """Evaluates command permission using the three-tier model.

    Optionally integrates with CapabilityPermissions for category-level blocking.

    Interactive Permission System:
    When tier="ask", broadcasts permission requests to all connected channels.
    Supports session-scoped approvals that last for the duration of a session.
    """

    def __init__(
        self,
        settings: SecuritySettings,
        capability_permissions=None,  # Optional[CapabilityPermissions]
    ) -> None:
        self._settings = settings
        self._approvals = ApprovalStore(settings.approvals_file)
        self._approval_callback: ApprovalCallback | None = None
        self._capability_permissions = capability_permissions
        # Session-scoped approvals: session_id -> set of approved commands
        self._session_approvals: dict[str, set[str]] = {}
        # Broadcaster for interactive permissions
        self._broadcaster = None

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        """Set the callback used to prompt the user when permission is 'ask'.

        Deprecated: Use set_broadcaster for interactive permissions.
        """
        self._approval_callback = callback

    def set_broadcaster(self, broadcaster) -> None:
        """Set the broadcaster for interactive permissions."""
        self._broadcaster = broadcaster

    def clear_session(self, session_id: str) -> None:
        """Clear session-scoped approvals when a session ends."""
        self._session_approvals.pop(session_id, None)

    async def check_command(
        self,
        command: str,
        session_id: str | None = None,
        platform: str | None = None,
        platform_chat_id: str | None = None,
        tool_name: str = "shell",
        skill_name: str | None = None,
        context: str | None = None,
    ) -> "PermissionResult":
        """Check whether a command is allowed to execute.

        Returns a PermissionResult with the decision and any relevant metadata.

        Check order:
        1. Blocked commands (hardcoded dangerous patterns)
        2. Capability permissions (YAML category-level rules)
        3. Session-scoped approvals (if session_id provided)
        4. Approval store (per-command glob rules)
        5. Default permission tier (ask / record / ignore)

        When tier="ask" and a broadcaster is available, broadcasts to all channels.
        """
        # Check blocked commands first
        if self._is_blocked(command):
            logger.warning("Command blocked by security policy: %s", command)
            return PermissionResult(
                allowed=False,
                tier="blocked",
                reason="Command matches a blocked pattern",
            )

        # Check capability-level permissions (from permissions.yaml)
        if self._capability_permissions is not None:
            allowed, reason = self._capability_permissions.check_command(command)
            if not allowed:
                return PermissionResult(
                    allowed=False,
                    tier="blocked",
                    reason=reason,
                )

        # Check session-scoped approvals
        if session_id and session_id in self._session_approvals:
            if command in self._session_approvals[session_id]:
                logger.info("Session approval found for: %s", command)
                return PermissionResult(
                    allowed=True,
                    tier="ask",
                    session_approved=True,
                )

        # Check approval store
        stored = self._approvals.check(command)
        if stored == "ignore":
            return PermissionResult(allowed=True, tier="ignore")
        if stored == "record":
            logger.info("RECORD: executing command: %s", command)
            return PermissionResult(allowed=True, tier="record")
        if stored == "ask":
            # Explicit "ask" rule — still need to prompt
            pass

        # Default permission tier
        tier = stored or self._settings.default_permission

        if tier == "ignore":
            return PermissionResult(allowed=True, tier="ignore")
        if tier == "record":
            logger.info("RECORD: executing command: %s", command)
            return PermissionResult(allowed=True, tier="record")

        # tier == "ask" — prompt the user
        # First try the new broadcaster-based interactive permission
        logger.debug(
            "Permission check for '%s': broadcaster=%s, session_id=%s, platform=%s, platform_chat_id=%s",
            command[:50],
            "yes" if self._broadcaster else "NO",
            session_id or "MISSING",
            platform or "MISSING",
            platform_chat_id or "MISSING",
        )
        if self._broadcaster and session_id and platform and platform_chat_id:
            logger.info(
                "Requesting interactive permission for command: %s (session=%s, platform=%s)",
                command,
                session_id,
                platform,
            )
            decision = await self._request_interactive_permission(
                command=command,
                session_id=session_id,
                platform=platform,
                platform_chat_id=platform_chat_id,
                tool_name=tool_name,
                skill_name=skill_name,
                context=context,
            )
            if decision == PermissionDecision.APPROVE_ONCE:
                return PermissionResult(allowed=True, tier="ask", user_approved=True)
            elif decision == PermissionDecision.APPROVE_SESSION:
                # Add to session approvals
                if session_id not in self._session_approvals:
                    self._session_approvals[session_id] = set()
                self._session_approvals[session_id].add(command)
                return PermissionResult(
                    allowed=True,
                    tier="ask",
                    session_approved=True,
                )
            else:  # DENY
                return PermissionResult(
                    allowed=False,
                    tier="ask",
                    reason="User denied command execution",
                )

        # Log why interactive permission is not available
        if not self._broadcaster:
            logger.debug("No broadcaster available for interactive permission")
        elif not session_id:
            logger.debug("No session_id available for interactive permission")
        elif not platform:
            logger.debug("No platform available for interactive permission")
        elif not platform_chat_id:
            logger.debug("No platform_chat_id available for interactive permission")

        # Fallback to legacy callback if available
        if self._approval_callback:
            approved = await self._approval_callback(command)
            if approved:
                # Remember this approval for next time
                self._approvals.add_rule(
                    pattern=command,
                    permission="ignore",
                    note="Approved by user via interactive prompt",
                )
                return PermissionResult(allowed=True, tier="ask", user_approved=True)
            else:
                return PermissionResult(
                    allowed=False,
                    tier="ask",
                    reason="User denied command execution",
                )

        # No callback available — deny by default
        logger.warning("No approval callback set; denying command: %s", command)
        return PermissionResult(
            allowed=False,
            tier="ask",
            reason="No interactive approval channel available",
        )

    async def _request_interactive_permission(
        self,
        command: str,
        session_id: str,
        platform: str,
        platform_chat_id: str,
        tool_name: str,
        skill_name: str | None,
        context: str | None,
    ) -> PermissionDecision:
        """Request permission via the broadcaster.

        Creates a PermissionRequest and broadcasts it to all channels.
        Returns the user's decision.
        """
        from steelclaw.security.permission_models import PermissionRequest

        request = PermissionRequest.create(
            command=command,
            tool_name=tool_name,
            session_id=session_id,
            platform=platform,
            platform_chat_id=platform_chat_id,
            skill_name=skill_name,
            context=context,
            timeout_seconds=self._settings.permission_timeout
            if hasattr(self._settings, "permission_timeout")
            else 300,
        )

        try:
            return await self._broadcaster.broadcast_request(request)
        except TimeoutError:
            logger.warning("Permission request timed out: %s", command)
            raise

    def _is_blocked(self, command: str) -> bool:
        """Check if the command matches any blocked pattern."""
        cmd_lower = command.lower().strip()
        for blocked in self._settings.blocked_commands:
            if blocked.lower() in cmd_lower:
                return True
        return False

    @property
    def approvals(self) -> ApprovalStore:
        return self._approvals


class PermissionResult:
    """Result of a permission check."""

    def __init__(
        self,
        allowed: bool,
        tier: str,
        reason: str = "",
        user_approved: bool = False,
        session_approved: bool = False,
    ) -> None:
        self.allowed = allowed
        self.tier = tier
        self.reason = reason
        self.user_approved = user_approved
        self.session_approved = session_approved

    def __bool__(self) -> bool:
        return self.allowed

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "tier": self.tier,
            "reason": self.reason,
            "user_approved": self.user_approved,
            "session_approved": self.session_approved,
        }
