"""Security context for propagating session/platform info across the call stack.

Uses contextvars to pass session context without modifying function signatures
throughout the entire codebase. This allows the permission system to access
session info when checking commands.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass

logger = logging.getLogger("steelclaw.security.context")


@dataclass
class SecurityContext:
    """Holds context for permission checks."""

    session_id: str | None = None
    platform: str | None = None
    platform_chat_id: str | None = None


# Context variable that propagates across async call boundaries
_current_context: ContextVar[SecurityContext] = ContextVar(
    "security_context",
    default=SecurityContext(),
)


def get_security_context() -> SecurityContext:
    """Get the current security context."""
    return _current_context.get()


def set_security_context(
    session_id: str | None = None,
    platform: str | None = None,
    platform_chat_id: str | None = None,
) -> None:
    """Set the security context for the current async task."""
    ctx = SecurityContext(
        session_id=session_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
    )
    _current_context.set(ctx)
    logger.debug(
        "Security context set: session_id=%s, platform=%s, platform_chat_id=%s",
        session_id,
        platform,
        platform_chat_id,
    )


def clear_security_context() -> None:
    """Clear the security context (reset to defaults)."""
    _current_context.set(SecurityContext())