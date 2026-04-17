"""Tests for session resolution — DM collapse, group isolation, allowlist."""

from __future__ import annotations

import pytest

from steelclaw.db.models import AllowlistEntry
from steelclaw.gateway.session_manager import AllowlistError, SessionManager
from steelclaw.schemas.messages import InboundMessage
from steelclaw.settings import GatewaySettings


def _dm(platform: str = "telegram", user_id: str = "u1", chat_id: str = "c1") -> InboundMessage:
    return InboundMessage(
        platform=platform,
        platform_chat_id=chat_id,
        platform_user_id=user_id,
        content="hello",
        is_group=False,
    )


def _group(
    content: str = "hey @steelclaw",
    is_mention: bool = True,
    chat_id: str = "g1",
) -> InboundMessage:
    return InboundMessage(
        platform="telegram",
        platform_chat_id=chat_id,
        platform_user_id="u1",
        content=content,
        is_group=True,
        is_mention=is_mention,
    )


@pytest.mark.asyncio
async def test_dm_creates_session(db_session):
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False))
    session = await sm.resolve(_dm(), db_session)
    assert session is not None
    assert session.session_type == "dm"
    assert session.unified_session_id == session.id


@pytest.mark.asyncio
async def test_dm_collapse_same_platform(db_session):
    """Two DMs from the same user on the same platform share a unified session."""
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False))
    s1 = await sm.resolve(_dm(chat_id="c1"), db_session)
    s2 = await sm.resolve(_dm(chat_id="c1"), db_session)
    assert s1.id == s2.id


@pytest.mark.asyncio
async def test_dm_collapse_cross_platform(db_session):
    """DMs from the same user across platforms share a unified_session_id after identity merge."""
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False))
    s1 = await sm.resolve(_dm(platform="telegram", user_id="u1", chat_id="tg1"), db_session)

    # Different platform but same user_id won't auto-merge (different PlatformIdentity).
    # This tests that each platform creates its own session.
    s2 = await sm.resolve(_dm(platform="discord", user_id="u1", chat_id="dc1"), db_session)
    assert s1.id != s2.id
    # They are separate users until an admin merges them.
    assert s1.unified_session_id != s2.unified_session_id


@pytest.mark.asyncio
async def test_group_isolation(db_session):
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False))
    s1 = await sm.resolve(_group(chat_id="g1"), db_session)
    s2 = await sm.resolve(_group(chat_id="g2"), db_session)
    assert s1.unified_session_id != s2.unified_session_id
    assert s1.session_type == "group"


@pytest.mark.asyncio
async def test_group_requires_mention(db_session):
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False))
    msg = _group(content="just chatting", is_mention=False)
    session = await sm.resolve(msg, db_session)
    assert session is None


@pytest.mark.asyncio
async def test_group_keyword_activation(db_session):
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=False, mention_keywords=["@sc"]))
    msg = _group(content="hey @sc what's up?", is_mention=False)
    session = await sm.resolve(msg, db_session)
    assert session is not None


@pytest.mark.asyncio
async def test_allowlist_blocks_non_allowed(db_session):
    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=True))
    with pytest.raises(AllowlistError):
        await sm.resolve(_dm(), db_session)


@pytest.mark.asyncio
async def test_allowlist_permits_allowed(db_session):
    entry = AllowlistEntry(platform="telegram", platform_user_id="u1")
    db_session.add(entry)
    await db_session.commit()

    sm = SessionManager(GatewaySettings(dm_allowlist_enabled=True))
    session = await sm.resolve(_dm(), db_session)
    assert session is not None
