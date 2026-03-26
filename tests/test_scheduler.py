"""Tests for the scheduler/task engine."""

from __future__ import annotations

import asyncio

import pytest

from steelclaw.scheduler.engine import TaskEngine
from steelclaw.settings import SchedulerSettings


@pytest.fixture()
async def engine():
    e = TaskEngine(SchedulerSettings(enabled=True))
    e.start()
    yield e
    e.stop()


@pytest.mark.asyncio
async def test_engine_starts_and_stops():
    e = TaskEngine(SchedulerSettings(enabled=True))
    e.start()
    assert e.running is True
    e.stop()
    assert e.running is False


def test_disabled_engine():
    e = TaskEngine(SchedulerSettings(enabled=False))
    e.start()
    assert e.running is False


@pytest.mark.asyncio
async def test_add_cron_job(engine):
    async def my_job():
        pass

    engine.add_cron_job("test-cron", my_job, "0 9 * * *", description="Daily 9am")
    jobs = engine.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == "test-cron"
    assert jobs[0]["type"] == "cron"


@pytest.mark.asyncio
async def test_add_interval_job(engine):
    async def my_job():
        pass

    engine.add_interval_job("test-interval", my_job, minutes=5, description="Every 5 min")
    jobs = engine.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["type"] == "interval"


@pytest.mark.asyncio
async def test_remove_job(engine):
    async def my_job():
        pass

    engine.add_cron_job("to-remove", my_job, "0 * * * *")
    assert engine.remove_job("to-remove") is True
    assert engine.list_jobs() == []
    assert engine.remove_job("nonexistent") is False


@pytest.mark.asyncio
async def test_invalid_cron_expression(engine):
    async def my_job():
        pass

    with pytest.raises(ValueError, match="Invalid cron"):
        engine.add_cron_job("bad", my_job, "not a cron")
