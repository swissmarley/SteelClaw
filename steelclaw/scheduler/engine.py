"""Proactive task engine — APScheduler integration for cron jobs and reminders."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from steelclaw.settings import SchedulerSettings

logger = logging.getLogger("steelclaw.scheduler")

TaskCallback = Callable[..., Coroutine[Any, Any, None]]


class TaskEngine:
    """Manages scheduled and proactive background tasks."""

    def __init__(self, settings: SchedulerSettings) -> None:
        self._settings = settings
        self._scheduler: AsyncIOScheduler | None = None
        self._task_registry: Dict[str, Dict[str, Any]] = {}

    def start(self) -> None:
        if not self._settings.enabled:
            logger.info("Scheduler disabled")
            return

        self._scheduler = AsyncIOScheduler(
            timezone=self._settings.timezone,
            job_defaults={
                "coalesce": True,
                "max_instances": self._settings.max_concurrent_jobs,
            },
        )
        self._scheduler.start()
        logger.info("Task engine started (timezone=%s)", self._settings.timezone)

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("Task engine stopped")

    def add_cron_job(
        self,
        job_id: str,
        func: TaskCallback,
        cron_expression: str,
        description: str = "",
        kwargs: dict | None = None,
    ) -> str:
        """Add a cron-scheduled job.

        cron_expression: "minute hour day month day_of_week"
        Examples: "0 9 * * *" (daily at 9am), "*/30 * * * *" (every 30 min)
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not started")

        parts = cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs or {},
        )
        self._task_registry[job_id] = {
            "type": "cron",
            "cron": cron_expression,
            "description": description,
        }
        logger.info("Added cron job: %s (%s) — %s", job_id, cron_expression, description)
        return job_id

    def add_interval_job(
        self,
        job_id: str,
        func: TaskCallback,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        description: str = "",
        kwargs: dict | None = None,
    ) -> str:
        """Add a recurring interval job."""
        if not self._scheduler:
            raise RuntimeError("Scheduler not started")

        trigger = IntervalTrigger(seconds=seconds, minutes=minutes, hours=hours)
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs or {},
        )
        self._task_registry[job_id] = {
            "type": "interval",
            "seconds": seconds + minutes * 60 + hours * 3600,
            "description": description,
        }
        logger.info("Added interval job: %s — %s", job_id, description)
        return job_id

    def add_one_time_job(
        self,
        job_id: str,
        func: TaskCallback,
        run_at: datetime,
        description: str = "",
        kwargs: dict | None = None,
    ) -> str:
        """Schedule a one-time reminder/task."""
        if not self._scheduler:
            raise RuntimeError("Scheduler not started")

        trigger = DateTrigger(run_date=run_at)
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs or {},
        )
        self._task_registry[job_id] = {
            "type": "once",
            "run_at": run_at.isoformat(),
            "description": description,
        }
        logger.info("Added one-time job: %s at %s — %s", job_id, run_at, description)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        if not self._scheduler:
            return False
        try:
            self._scheduler.remove_job(job_id)
            self._task_registry.pop(job_id, None)
            return True
        except Exception:
            return False

    def list_jobs(self) -> list[dict]:
        jobs = []
        for job_id, meta in self._task_registry.items():
            info = {"id": job_id, **meta}
            if self._scheduler:
                job = self._scheduler.get_job(job_id)
                if job:
                    info["next_run"] = str(job.next_run_time)
            jobs.append(info)
        return jobs

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running
