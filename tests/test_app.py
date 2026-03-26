"""Tests for the FastAPI application — health, info, lifespan."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_info(lifespan_client):
    resp = await lifespan_client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "connectors" in data
