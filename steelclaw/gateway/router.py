"""Gateway router — WebSocket endpoint, webhook receiver, and central message pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import Message as DBMessage, Session as DBSession
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
_memory_ingestor = None  # Will be set from app lifespan
_connector_registry = None  # Will be set from app lifespan


def set_agent_router(agent_router: object) -> None:
    """Called during app startup to inject the LLM-powered agent router."""
    global _agent_router
    _agent_router = agent_router


def set_memory_ingestor(ingestor: object) -> None:
    """Called during app startup to inject the memory ingestor."""
    global _memory_ingestor
    _memory_ingestor = ingestor


def set_connector_registry(registry: object) -> None:
    """Called during app startup to inject the connector registry."""
    global _connector_registry
    _connector_registry = registry


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

    # Update session activity
    now = datetime.now(timezone.utc)
    session.last_activity_at = now
    session.updated_at = now
    if session.status == "idle":
        session.status = "active"

    # Persist inbound message (with attachment metadata if present)
    msg_metadata = None
    if inbound.attachments:
        msg_metadata = json.dumps({
            "attachments": [
                {"filename": a.get("filename"), "category": a.get("category"), "mime": a.get("mime")}
                for a in inbound.attachments
            ]
        })
    db_msg = DBMessage(
        session_id=session.id,
        role="user",
        content=inbound.content,
        platform=inbound.platform,
        platform_message_id=inbound.platform_message_id,
        metadata_json=msg_metadata,
    )
    db.add(db_msg)
    await db.commit()

    # Route to agent (pass db so the agent can load conversation history)
    if _agent_router is not None:
        agent_result = await _agent_router.route_with_usage(inbound, session, db=db)
        outbound = agent_result.outbound

        # Persist outbound message with usage metadata
        db_reply = DBMessage(
            session_id=session.id,
            role="assistant",
            content=outbound.content,
            platform=outbound.platform,
            model=agent_result.model,
            token_usage_prompt=agent_result.token_usage_prompt,
            token_usage_completion=agent_result.token_usage_completion,
            cost_usd=agent_result.cost_usd,
        )
    else:
        # Fallback echo if agent not initialised
        outbound = OutboundMessage(
            platform=inbound.platform,
            platform_chat_id=inbound.platform_chat_id,
            content=f"[echo] {inbound.content}",
        )
        db_reply = DBMessage(
            session_id=session.id,
            role="assistant",
            content=outbound.content,
            platform=outbound.platform,
        )

    db.add(db_reply)
    await db.commit()

    # Ingest into memory scoped to unified session (non-blocking, errors swallowed)
    if _memory_ingestor is not None:
        try:
            namespace = session.unified_session_id or session.id
            await _memory_ingestor.ingest_exchange(
                user_message=inbound.content,
                assistant_message=outbound.content,
                session_id=session.id,
                namespace=namespace,
                db=db,
            )
        except Exception:
            logger.debug("Memory ingestion failed (non-critical)", exc_info=True)

    return outbound


async def process_message_streaming(
    inbound: InboundMessage,
    settings: GatewaySettings,
    db: AsyncSession,
):
    """Streaming pipeline: resolves session, persists, then yields agent stream events.

    Yields dicts from AgentRouter.stream_response() plus handles persistence
    once the stream completes.
    """
    sm = _get_session_manager(settings)
    session = await sm.resolve(inbound, db)
    if session is None:
        yield {"type": "error", "content": "Could not resolve session."}
        return

    now = datetime.now(timezone.utc)
    session.last_activity_at = now
    session.updated_at = now
    if session.status == "idle":
        session.status = "active"

    # Persist inbound message
    msg_metadata = None
    if inbound.attachments:
        msg_metadata = json.dumps({
            "attachments": [
                {"filename": a.get("filename"), "category": a.get("category"), "mime": a.get("mime")}
                for a in inbound.attachments
            ]
        })
    db_msg = DBMessage(
        session_id=session.id,
        role="user",
        content=inbound.content,
        platform=inbound.platform,
        platform_message_id=inbound.platform_message_id,
        metadata_json=msg_metadata,
    )
    db.add(db_msg)
    await db.commit()

    if _agent_router is None:
        yield {"type": "chunk", "content": f"[echo] {inbound.content}"}
        yield {"type": "done", "content": f"[echo] {inbound.content}", "usage": {}}
        return

    full_content = ""
    usage = {}

    async for event in _agent_router.stream_response(inbound, session, db=db):
        if event["type"] == "chunk":
            full_content += event["content"]
        elif event["type"] == "done":
            full_content = event.get("content", full_content)
            usage = event.get("usage", {})
        elif event["type"] == "error":
            full_content = event.get("content", full_content or "An error occurred.")
        yield event

    # Persist outbound message
    from steelclaw.pricing import calculate_cost

    model = usage.get("model")
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    db_reply = DBMessage(
        session_id=session.id,
        role="assistant",
        content=full_content,
        platform=inbound.platform,
        model=model,
        token_usage_prompt=prompt_tokens,
        token_usage_completion=completion_tokens,
        cost_usd=calculate_cost(model, prompt_tokens, completion_tokens),
    )
    db.add(db_reply)
    await db.commit()

    # Ingest into memory
    if _memory_ingestor is not None:
        try:
            namespace = session.unified_session_id or session.id
            await _memory_ingestor.ingest_exchange(
                user_message=inbound.content,
                assistant_message=full_content,
                session_id=session.id,
                namespace=namespace,
                db=db,
            )
        except Exception:
            logger.debug("Memory ingestion failed (non-critical)", exc_info=True)


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

            # Check if client supports streaming
            stream_mode = data.get("stream", False)

            # Resolve file attachments from upload IDs
            attachments = None
            raw_attachments = data.get("attachments")
            if raw_attachments:
                from steelclaw.api.files import get_upload, cleanup_upload

                attachments = []
                for att in raw_attachments:
                    file_id = att.get("id") if isinstance(att, dict) else att
                    upload = get_upload(file_id) if file_id else None
                    if upload:
                        attachments.append(upload)
                        cleanup_upload(file_id)

            inbound = InboundMessage(
                platform="websocket",
                platform_chat_id=conn_id,
                platform_user_id=data.get("user_id", conn_id),
                platform_username=data.get("username"),
                content=data.get("content", ""),
                attachments=attachments if attachments else None,
                is_group=False,
                is_mention=False,
            )

            if stream_mode:
                # Streaming mode — send incremental chunks
                try:
                    async for db in get_async_session():
                        settings = websocket.app.state.settings
                        async for event in process_message_streaming(
                            inbound, settings.gateway, db
                        ):
                            await websocket.send_text(json.dumps(event))
                except Exception:
                    logger.exception("Error in streaming WebSocket message")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "content": "I encountered an internal error. Please try again.",
                    }))
            else:
                # Legacy non-streaming mode — full response at once
                outbound = None
                try:
                    async for db in get_async_session():
                        settings = websocket.app.state.settings
                        outbound = await process_message(inbound, settings.gateway, db)
                except Exception:
                    logger.exception("Error processing WebSocket message")
                    outbound = OutboundMessage(
                        platform="websocket",
                        platform_chat_id=conn_id,
                        content="I encountered an internal error. Please try again.",
                    )

                if outbound:
                    await websocket.send_text(json.dumps({"content": outbound.content}))

    except WebSocketDisconnect:
        # Mark the WebSocket session as closed
        async for db in get_async_session():
            from sqlalchemy import select
            stmt = select(DBSession).where(
                DBSession.platform == "websocket",
                DBSession.platform_chat_id == conn_id,
                DBSession.status == "active",
            )
            result = await db.execute(stmt)
            ws_session = result.scalar_one_or_none()
            if ws_session:
                ws_session.status = "closed"
                ws_session.updated_at = datetime.now(timezone.utc)
                await db.commit()
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
