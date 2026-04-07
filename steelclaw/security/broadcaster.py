"""Cross-channel permission request broadcasting.

Broadcasts permission requests to all connected channels (WebUI, CLI, Telegram,
Discord, Slack) and coordinates responses using first-response-wins semantics.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Callable

from steelclaw.security.permission_models import (
    PermissionDecision,
    PermissionRequest,
    PermissionResponse,
    PermissionRequestStatus,
    ResolvedRequest,
)

if TYPE_CHECKING:
    from steelclaw.gateway.base import BaseConnector
    from steelclaw.gateway.registry import ConnectorRegistry

logger = logging.getLogger("steelclaw.security.broadcaster")


class PermissionBroadcaster:
    """Broadcasts permission requests to all channels and awaits responses.

    Uses first-response-wins semantics. When any user responds, all other
    channels receive a permission_resolved message to dismiss their UI.
    """

    def __init__(self, timeout_seconds: int = 300) -> None:
        self._timeout = timeout_seconds
        self._pending_requests: dict[str, PermissionRequest] = {}
        self._pending_responses: dict[str, asyncio.Event] = {}
        self._resolved_requests: dict[str, ResolvedRequest] = {}
        self._connector_registry: Optional["ConnectorRegistry"] = None
        # Function to get WebSocket connections dynamically
        self._get_ws_connections: Optional[Callable[[], set]] = None

    def set_ws_connections_getter(self, getter: Callable[[], set]) -> None:
        """Set function to get WebSocket connections. Called from gateway/router.py."""
        self._get_ws_connections = getter

    def set_connector_registry(self, registry: "ConnectorRegistry") -> None:
        """Set connector registry reference. Called during app startup."""
        self._connector_registry = registry

    async def broadcast_request(self, request: PermissionRequest) -> PermissionDecision:
        """Broadcast a permission request to all channels and await response.

        Returns the decision (approve_once, approve_session, or deny).
        Raises TimeoutError if no response within timeout.
        """
        logger.info("Broadcasting permission request for command: %s", request.command)
        self._pending_requests[request.request_id] = request
        response_event = asyncio.Event()
        self._pending_responses[request.request_id] = response_event

        try:
            # Broadcast to WebSocket clients
            await self._broadcast_to_websockets(request)

            # Broadcast to platform connectors
            await self._broadcast_to_connectors(request)

            # Wait for response with timeout
            try:
                await asyncio.wait_for(
                    response_event.wait(),
                    timeout=request.timeout_seconds,
                )
            except asyncio.TimeoutError:
                request.status = PermissionRequestStatus.TIMEOUT
                logger.warning(
                    "Permission request %s timed out after %ds",
                    request.request_id,
                    request.timeout_seconds,
                )
                raise

            # Get the resolved decision
            resolved = self._resolved_requests.get(request.request_id)
            if resolved:
                request.status = PermissionRequestStatus.APPROVED
                logger.info("Permission request %s resolved: %s", request.request_id, resolved.decision)
                return resolved.decision

            # Should not happen
            raise RuntimeError("Request resolved but no decision found")

        finally:
            # Cleanup
            self._pending_requests.pop(request.request_id, None)
            self._pending_responses.pop(request.request_id, None)
            self._resolved_requests.pop(request.request_id, None)

    async def resolve_request(self, response: PermissionResponse) -> bool:
        """Handle a user's response to a permission request.

        Returns True if this was the first response (wins), False if already resolved.
        Broadcasts permission_resolved to all channels to dismiss UI.
        """
        request = self._pending_requests.get(response.request_id)
        if not request:
            logger.warning(
                "Received response for unknown request %s",
                response.request_id,
            )
            return False

        # Check if already resolved (first-response-wins)
        if request.request_id in self._resolved_requests:
            return False

        # Create resolved request
        decision = response.decision
        if decision == PermissionDecision.DENY:
            request.status = PermissionRequestStatus.DENIED
        else:
            request.status = PermissionRequestStatus.APPROVED

        resolved = ResolvedRequest(
            request_id=response.request_id,
            decision=decision,
            resolved_by=f"{response.platform}:{response.user_id}",
            original_command=request.command,
        )
        self._resolved_requests[request.request_id] = resolved

        # Signal the waiting broadcast_request() call
        event = self._pending_responses.get(response.request_id)
        if event:
            event.set()

        # Broadcast resolution to all channels
        await self._broadcast_resolution(resolved)

        return True

    async def clear_session_approvals(self, session_id: str) -> None:
        """Clear session-scoped approvals when a session ends.

        Called from session_heartbeat.py when a session transitions to 'closed'.
        """
        # This is managed by PermissionManager, not the broadcaster
        # The broadcaster just coordinates responses
        pass

    async def _broadcast_to_websockets(self, request: PermissionRequest) -> None:
        """Send permission_request message to all WebSocket clients."""
        ws_connections = None
        if self._get_ws_connections:
            try:
                ws_connections = self._get_ws_connections()
            except Exception:
                pass

        if not ws_connections:
            logger.debug("No WebSocket connections available for permission broadcast")
            return

        message = {
            "type": "permission_request",
            "data": request.to_dict(),
        }

        logger.info("Broadcasting permission request %s to %d WebSocket clients", request.request_id, len(ws_connections))

        # Broadcast to all connected WebSocket clients
        for ws in list(ws_connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug("Failed to send to WebSocket: %s", e)

    async def _broadcast_to_connectors(self, request: PermissionRequest) -> None:
        """Send permission request to all platform connectors."""
        if not self._connector_registry:
            return

        request_data = request.to_dict()

        for platform, connector in self._connector_registry._connectors.items():
            try:
                await connector.send_permission_request(
                    request.platform_chat_id,
                    request_data,
                )
            except Exception as e:
                logger.warning(
                    "Failed to send permission request to %s: %s",
                    platform,
                    e,
                )

    async def _broadcast_resolution(self, resolved: ResolvedRequest) -> None:
        """Broadcast permission_resolved to dismiss UI on other channels."""
        message = {
            "type": "permission_resolved",
            "data": resolved.to_dict(),
        }

        # Broadcast to WebSockets
        ws_connections = None
        if self._get_ws_connections:
            try:
                ws_connections = self._get_ws_connections()
            except Exception:
                pass

        if ws_connections:
            for ws in list(ws_connections):
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

        # Broadcast to connectors
        if self._connector_registry:
            for platform, connector in self._connector_registry._connectors.items():
                try:
                    await connector.send_permission_request(
                        "",  # No specific chat_id for resolution broadcast
                        message,
                    )
                except Exception:
                    pass


# Global broadcaster instance
_broadcaster: Optional[PermissionBroadcaster] = None


def get_broadcaster() -> Optional[PermissionBroadcaster]:
    """Get the global broadcaster instance."""
    return _broadcaster


def set_broadcaster(broadcaster: PermissionBroadcaster) -> None:
    """Set the global broadcaster instance."""
    global _broadcaster
    _broadcaster = broadcaster