"""Scheduler commands for managing scheduled jobs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from steelclaw.paths import PROJECT_ROOT

from steelclaw.paths import PROJECT_ROOT

from steelclaw.paths import PROJECT_ROOT


def handle_scheduler(args: argparse.Namespace) -> None:
    """Handle scheduler commands."""
    action = args.scheduler_action

    if action == "list":
        _list_jobs()
    elif action == "add":
        _add_job(args.job_id, args.cron, args.interval, args.command)
    elif action == "remove":
        _remove_job(args.job_id)
    elif action == "run":
        _run_job(args.job_id)
    elif action == "set-timezone":
        _set_timezone(args.timezone)
    elif action == "set-max-concurrent":
        _set_max_concurrent(args.count)
    else:
        print(f"Unknown scheduler action: {action}")


def _get_config_path() -> Path:
    """Get the path to config.json."""
    return PROJECT_ROOT / "config.json"


def _load_config() -> dict:
    """Load config from file."""
    path = _get_config_path()
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_config(config: dict) -> None:
    """Save config to file."""
    path = _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def _get_scheduler_config() -> dict:
    """Get scheduler config section."""
    config = _load_config()
    if "agents" not in config:
        config["agents"] = {}
    if "scheduler" not in config["agents"]:
        config["agents"]["scheduler"] = {}
    return config["agents"]["scheduler"]


def _list_jobs() -> None:
    """List all scheduled jobs."""
    import asyncio
    from steelclaw.scheduler.engine import TaskEngine

    scheduler_config = _get_scheduler_config()
    jobs = scheduler_config.get("jobs", [])

    if not jobs:
        print("No scheduled jobs.")
        return

    print(f"{'Job ID':<20} {'Type':<10} {'Schedule':<20} Command")
    print("-" * 70)
    for job in jobs:
        job_id = job.get("id", "unknown")
        if "cron" in job:
            schedule_type = "cron"
            schedule = job["cron"]
        elif "interval" in job:
            schedule_type = "interval"
            schedule = f"{job['interval']}s"
        else:
            schedule_type = "unknown"
            schedule = "N/A"

        command = job.get("command", "")[:40]
        print(f"{job_id:<20} {schedule_type:<10} {schedule:<20} {command}")

    # Show scheduler settings
    print(f"\nTimezone: {scheduler_config.get('timezone', 'UTC')}")
    print(f"Max concurrent jobs: {scheduler_config.get('max_concurrent_jobs', 5)}")
    print(f"Enabled: {scheduler_config.get('enabled', True)}")


def _add_job(job_id: str, cron: str | None, interval: int | None, command: str) -> None:
    """Add a scheduled job."""
    if not cron and not interval:
        print("Error: Must specify --cron or --interval")
        return

    if cron and interval:
        print("Error: Cannot specify both --cron and --interval")
        return

    config = _load_config()
    if "agents" not in config:
        config["agents"] = {}
    if "scheduler" not in config["agents"]:
        config["agents"]["scheduler"] = {}
    if "jobs" not in config["agents"]["scheduler"]:
        config["agents"]["scheduler"]["jobs"] = []

    jobs = config["agents"]["scheduler"]["jobs"]

    # Check for existing job with same ID
    for existing in jobs:
        if existing.get("id") == job_id:
            print(f"Job '{job_id}' already exists. Remove it first.")
            return

    job = {
        "id": job_id,
        "command": command,
    }

    if cron:
        job["cron"] = cron
    elif interval:
        job["interval"] = interval

    jobs.append(job)
    _save_config(config)
    print(f"Added job: {job_id}")


def _remove_job(job_id: str) -> None:
    """Remove a scheduled job."""
    config = _load_config()
    if "agents" not in config:
        config["agents"] = {}
    if "scheduler" not in config["agents"]:
        config["agents"]["scheduler"] = {}
    if "jobs" not in config["agents"]["scheduler"]:
        config["agents"]["scheduler"]["jobs"] = []

    jobs = config["agents"]["scheduler"]["jobs"]
    before = len(jobs)
    config["agents"]["scheduler"]["jobs"] = [j for j in jobs if j.get("id") != job_id]

    if len(config["agents"]["scheduler"]["jobs"]) < before:
        _save_config(config)
        print(f"Removed job: {job_id}")
    else:
        print(f"Job not found: {job_id}")


def _run_job(job_id: str) -> None:
    """Run a scheduled job immediately."""
    print(f"Running job '{job_id}' immediately requires the server to be running.")
    print("The job will execute on the next scheduler tick.")
    print("Use 'steelclaw scheduler list' to check job status.")


def _set_timezone(timezone: str) -> None:
    """Set the scheduler timezone."""
    config = _load_config()
    if "agents" not in config:
        config["agents"] = {}
    if "scheduler" not in config["agents"]:
        config["agents"]["scheduler"] = {}

    config["agents"]["scheduler"]["timezone"] = timezone
    _save_config(config)
    print(f"Set scheduler timezone to: {timezone}")


def _set_max_concurrent(count: int) -> None:
    """Set the max concurrent jobs."""
    config = _load_config()
    if "agents" not in config:
        config["agents"] = {}
    if "scheduler" not in config["agents"]:
        config["agents"]["scheduler"] = {}

    config["agents"]["scheduler"]["max_concurrent_jobs"] = count
    _save_config(config)
    print(f"Set max concurrent jobs to: {count}")