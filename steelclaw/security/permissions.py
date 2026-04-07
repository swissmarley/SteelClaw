"""Three-tier permission model for command execution.

Tiers:
  - "ask":    Prompt the user via WebSocket before executing.
  - "record": Log the action but allow execution.
  - "ignore": Auto-allow silently.

Extended capability permissions from ~/.steelclaw/permissions.yaml are checked
*before* the approval store, allowing category-level (network, packages, etc.)
blocking independent of individual command rules.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Optional

from steelclaw.security.approvals import ApprovalStore
from steelclaw.settings import SecuritySettings

logger = logging.getLogger("steelclaw.security.permissions")

# Callback type: async fn(command) -> bool (True = approved, False = denied)
ApprovalCallback = Callable[[str], Coroutine[Any, Any, bool]]


class PermissionManager:
    """Evaluates command permission using the three-tier model.

    Optionally integrates with CapabilityPermissions for category-level blocking.
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

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        """Set the callback used to prompt the user when permission is 'ask'."""
        self._approval_callback = callback

    async def check_command(self, command: str) -> PermissionResult:
        """Check whether a command is allowed to execute.

        Returns a PermissionResult with the decision and any relevant metadata.

        Check order:
        1. Blocked commands (hardcoded dangerous patterns)
        2. Capability permissions (YAML category-level rules)
        3. Approval store (per-command glob rules)
        4. Default permission tier (ask / record / ignore)
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
    ) -> None:
        self.allowed = allowed
        self.tier = tier
        self.reason = reason
        self.user_approved = user_approved

    def __bool__(self) -> bool:
        return self.allowed

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "tier": self.tier,
            "reason": self.reason,
            "user_approved": self.user_approved,
        }
