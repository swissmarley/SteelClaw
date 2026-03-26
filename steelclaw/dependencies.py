"""FastAPI dependency injection providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.settings import Settings


async def get_db(session: AsyncSession = Depends(get_async_session)) -> AsyncIterator[AsyncSession]:
    yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request):
    from steelclaw.gateway.registry import ConnectorRegistry

    registry: ConnectorRegistry = request.app.state.registry
    return registry
