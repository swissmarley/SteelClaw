"""Session resolution — DM collapse, group isolation, allowlist enforcement."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.models import AllowlistEntry, PlatformIdentity, Session as DBSession, User
from steelclaw.schemas.messages import InboundMessage
from steelclaw.settings import GatewaySettings

logger = logging.getLogger("steelclaw.gateway.sessions")


class SessionManager:
    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    # ── Public API ──────────────────────────────────────────────────────

    async def resolve(self, msg: InboundMessage, db: AsyncSession) -> DBSession | None:
        """Return the session for *msg*, or ``None`` if the message should be dropped."""

        if msg.is_group:
            if not msg.is_mention and not self._has_keyword(msg.content):
                return None
            return await self._resolve_group_session(msg, db)

        # DM path
        if self._settings.dm_allowlist_enabled:
            if not await self._is_allowed(msg.platform, msg.platform_user_id, db):
                logger.debug(
                    "Dropping DM from non-allowlisted user %s/%s",
                    msg.platform,
                    msg.platform_user_id,
                )
                return None

        return await self._resolve_dm_session(msg, db)

    # ── DM session resolution ───────────────────────────────────────────

    async def _resolve_dm_session(self, msg: InboundMessage, db: AsyncSession) -> DBSession:
        identity = await self._get_or_create_identity(msg, db)
        user = identity.user

        # Look for an existing DM session on this exact platform + chat
        stmt = select(DBSession).where(
            DBSession.platform == msg.platform,
            DBSession.platform_chat_id == msg.platform_chat_id,
            DBSession.session_type == "dm",
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        if session:
            return session

        # Find a unified_session_id from any existing DM session for this user
        existing_stmt = select(DBSession.unified_session_id).where(
            DBSession.user_id == user.id,
            DBSession.session_type == "dm",
            DBSession.unified_session_id.isnot(None),
        ).limit(1)
        existing_result = await db.execute(existing_stmt)
        unified_id = existing_result.scalar_one_or_none()

        new_session = DBSession(
            platform=msg.platform,
            platform_chat_id=msg.platform_chat_id,
            session_type="dm",
            user_id=user.id,
            connector_type=msg.platform,
            status="active",
        )
        db.add(new_session)
        await db.flush()  # populate new_session.id

        new_session.unified_session_id = unified_id or new_session.id
        await db.commit()
        await db.refresh(new_session)
        return new_session

    # ── Group session resolution ────────────────────────────────────────

    async def _resolve_group_session(self, msg: InboundMessage, db: AsyncSession) -> DBSession:
        stmt = select(DBSession).where(
            DBSession.platform == msg.platform,
            DBSession.platform_chat_id == msg.platform_chat_id,
            DBSession.session_type == "group",
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        if session:
            return session

        new_session = DBSession(
            platform=msg.platform,
            platform_chat_id=msg.platform_chat_id,
            session_type="group",
            connector_type=msg.platform,
            status="active",
        )
        db.add(new_session)
        await db.flush()
        new_session.unified_session_id = new_session.id  # isolated
        await db.commit()
        await db.refresh(new_session)
        return new_session

    # ── Helpers ─────────────────────────────────────────────────────────

    def _has_keyword(self, content: str) -> bool:
        lower = content.lower()
        return any(kw.lower() in lower for kw in self._settings.mention_keywords)

    async def _is_allowed(self, platform: str, platform_user_id: str, db: AsyncSession) -> bool:
        stmt = select(AllowlistEntry).where(
            AllowlistEntry.platform == platform,
            AllowlistEntry.platform_user_id == platform_user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _get_or_create_identity(
        self, msg: InboundMessage, db: AsyncSession
    ) -> PlatformIdentity:
        stmt = (
            select(PlatformIdentity)
            .where(
                PlatformIdentity.platform == msg.platform,
                PlatformIdentity.platform_user_id == msg.platform_user_id,
            )
        )
        result = await db.execute(stmt)
        identity = result.scalar_one_or_none()
        if identity:
            # Eagerly load user
            await db.refresh(identity, ["user"])
            return identity

        user = User(
            display_name=msg.platform_username or f"{msg.platform}:{msg.platform_user_id}",
        )
        db.add(user)
        await db.flush()

        identity = PlatformIdentity(
            user_id=user.id,
            platform=msg.platform,
            platform_user_id=msg.platform_user_id,
            platform_username=msg.platform_username,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity, ["user"])
        return identity
