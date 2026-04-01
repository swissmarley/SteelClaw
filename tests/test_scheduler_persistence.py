"""Tests for the scheduler persistence layer."""

from __future__ import annotations

import json

import pytest

from steelclaw.scheduler.persistence import (
    add_schedule,
    get_schedule,
    load_schedules,
    remove_schedule,
    save_schedules,
    update_schedule_field,
)


@pytest.fixture(autouse=True)
def _patch_path(tmp_path, monkeypatch):
    """Redirect SCHEDULES_PATH to a temp directory for every test."""
    monkeypatch.setattr(
        "steelclaw.scheduler.persistence.SCHEDULES_PATH",
        tmp_path / "schedules.json",
    )


def test_load_schedules_no_file():
    """Missing file should return empty list."""
    assert load_schedules() == []


def test_save_and_load_round_trip():
    schedules = [{"id": "job1", "type": "cron", "cron": "0 9 * * *"}]
    save_schedules(schedules)
    loaded = load_schedules()
    assert len(loaded) == 1
    assert loaded[0]["id"] == "job1"


def test_add_schedule_new():
    add_schedule({"id": "a", "type": "interval", "seconds": 60})
    assert len(load_schedules()) == 1


def test_add_schedule_replaces_existing():
    add_schedule({"id": "a", "type": "interval", "seconds": 60})
    add_schedule({"id": "a", "type": "interval", "seconds": 120})
    schedules = load_schedules()
    assert len(schedules) == 1
    assert schedules[0]["seconds"] == 120


def test_remove_schedule_found():
    add_schedule({"id": "x", "type": "cron"})
    assert remove_schedule("x") is True
    assert load_schedules() == []


def test_remove_schedule_not_found():
    assert remove_schedule("nonexistent") is False


def test_get_schedule_found():
    add_schedule({"id": "g1", "type": "once", "run_at": "2026-04-01T10:00:00"})
    s = get_schedule("g1")
    assert s is not None
    assert s["type"] == "once"


def test_get_schedule_not_found():
    assert get_schedule("missing") is None


def test_update_schedule_field_found():
    add_schedule({"id": "u1", "type": "cron", "description": "old"})
    assert update_schedule_field("u1", "description", "new") is True
    s = get_schedule("u1")
    assert s["description"] == "new"


def test_update_schedule_field_not_found():
    assert update_schedule_field("missing", "x", "y") is False


def test_load_schedules_corrupt_file(tmp_path, monkeypatch):
    """Corrupt JSON should return empty list."""
    path = tmp_path / "bad_schedules.json"
    path.write_text("{not valid", encoding="utf-8")
    monkeypatch.setattr(
        "steelclaw.scheduler.persistence.SCHEDULES_PATH", path
    )
    assert load_schedules() == []
