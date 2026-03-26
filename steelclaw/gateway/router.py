"""Gateway router — WebSocket endpoint, webhook receiver, and central message pipeline."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Message as DBMessage
from steelclaw.gateway.session_manager import SessionManager
from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import GatewaySettings, Settings

logger = logging.getLogger("steelclaw.gateway.router")

router = APIRouter()

# Active WebSocket connections: conn_id → WebSocket
_ws_connections: dict[str, WebSocket] = {}

# Module-level singletons — initialised via set_agent_router()
_session_manager: SessionManager | None = None
_agent_router = None  # Will be set from app lifespan


def set_agent_router(agent_router: object) -> None:
    """Called during app startup to inject the LLM-powered agent router."""
    global _agent_router
    _agent_router = agent_router


def _get_session_manager(settings: GatewaySettings) -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(settings)
    return _session_manager


# ── Central message pipeline ────────────────────────────────────────────────


async def process_message(
    inbound: InboundMessage,
    settings: GatewaySettings,
    db: AsyncSession,
) -> OutboundMessage | None:
    """Full pipeline: session resolution → persist → agent → respond."""
    sm = _get_session_manager(settings)

    session = await sm.resolve(inbound, db)
    if session is None:
        return None

    # Persist inbound message
    db_msg = DBMessage(
        session_id=session.id,
        role="user",
        content=inbound.content,
        platform=inbound.platform,
        platform_message_id=inbound.platform_message_id,
    )
    db.add(db_msg)
    await db.commit()

    # Route to agent (pass db so the agent can load conversation history)
    if _agent_router is not None:
        outbound = await _agent_router.route(inbound, session, db=db)
    else:
        # Fallback echo if agent not initialised
        outbound = OutboundMessage(
            platform=inbound.platform,
            platform_chat_id=inbound.platform_chat_id,
            content=f"[echo] {inbound.content}",
        )

    # Persist outbound message
    db_reply = DBMessage(
        session_id=session.id,
        role="assistant",
        content=outbound.content,
        platform=outbound.platform,
    )
    db.add(db_reply)
    await db.commit()

    return outbound


# ── WebSocket endpoint ──────────────────────────────────────────────────────


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    conn_id = str(uuid.uuid4())
    _ws_connections[conn_id] = websocket
    logger.info("WebSocket connected: %s", conn_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"content": raw}

            inbound = InboundMessage(
                platform="websocket",
                platform_chat_id=conn_id,
                platform_user_id=data.get("user_id", conn_id),
                platform_username=data.get("username"),
                content=data.get("content", ""),
                is_group=False,
                is_mention=False,
            )

            # Get a fresh DB session for each message
            async for db in get_async_session():
                settings = websocket.app.state.settings
                outbound = await process_message(inbound, settings.gateway, db)

            if outbound:
                await websocket.send_text(json.dumps({"content": outbound.content}))
    except WebSocketDisconnect:
        pass
    finally:
        _ws_connections.pop(conn_id, None)
        logger.info("WebSocket disconnected: %s", conn_id)


def get_ws_connections() -> dict[str, WebSocket]:
    """Expose active WS connections for the approval callback."""
    return _ws_connections


# ── Webhook receiver ────────────────────────────────────────────────────────


@router.post("/webhook/{platform}")
async def webhook_receiver(platform: str) -> dict:
    """Placeholder for platforms that push via webhooks (Slack, Teams, etc.)."""
    return {"status": "ok", "platform": platform}
