"""Shared test fixtures — in-memory async SQLite."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from steelclaw.app import create_app
from steelclaw.db import engine as engine_mod
from steelclaw.settings import DatabaseSettings, GatewaySettings, Settings


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def db_engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url="sqlite+aiosqlite://", echo=False),
        gateway=GatewaySettings(dm_allowlist_enabled=False),
    )


@pytest.fixture()
async def app(test_settings):
    application = create_app(test_settings)
    return application


@pytest.fixture()
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def lifespan_client(app) -> AsyncIterator[AsyncClient]:
    """Client that runs the full lifespan (DB init, connector start, etc.)."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
