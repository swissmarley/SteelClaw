"""REST API for tool management (formerly Skills API — Phase 1 rename)."""

# Phase 1 renamed "Skills" → "Tools" in user-facing surfaces.
# The underlying module remains skills.py for backward compatibility;
# this module re-exports the same router under the new name.
from steelclaw.api.skills import router  # noqa: F401

__all__ = ["router"]