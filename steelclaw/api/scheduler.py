"""REST API for scheduler/task management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class CronJobRequest(BaseModel):
    job_id: str
    cron_expression: str
    command: str
    description: str = ""


class IntervalJobRequest(BaseModel):
    job_id: str
    seconds: int = 0
    minutes: int = 0
    hours: int = 0
    command: str
    description: str = ""


@router.get("/jobs")
async def list_jobs(request: Request) -> list[dict]:
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    return engine.list_jobs()


@router.delete("/jobs/{job_id}")
async def remove_job(job_id: str, request: Request) -> dict:
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    if engine.remove_job(job_id):
        return {"status": "removed", "job_id": job_id}
    raise HTTPException(404, f"Job '{job_id}' not found")


@router.get("/status")
async def scheduler_status(request: Request) -> dict:
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    return {
        "running": engine.running,
        "jobs_count": len(engine.list_jobs()),
    }


@router.post("/jobs/cron")
async def add_cron_job(req: CronJobRequest, request: Request) -> dict:
    """Add a cron-based scheduled job."""
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    try:
        engine.add_cron_job(
            job_id=req.job_id,
            cron_expr=req.cron_expression,
            command=req.command,
        )
        return {"status": "added", "job_id": req.job_id, "type": "cron"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/jobs/interval")
async def add_interval_job(req: IntervalJobRequest, request: Request) -> dict:
    """Add an interval-based scheduled job."""
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    interval_seconds = req.seconds + (req.minutes * 60) + (req.hours * 3600)
    if interval_seconds < 1:
        raise HTTPException(400, "Interval must be at least 1 second")

    try:
        engine.add_interval_job(
            job_id=req.job_id,
            func=lambda: None,  # Placeholder, command is stored in config
            seconds=interval_seconds,
        )
        return {"status": "added", "job_id": req.job_id, "type": "interval", "seconds": interval_seconds}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/jobs/{job_id}/run")
async def run_job(job_id: str, request: Request) -> dict:
    """Trigger a scheduled job to run immediately."""
    from steelclaw.scheduler.engine import TaskEngine

    engine: TaskEngine = request.app.state.task_engine
    if engine.trigger_job(job_id):
        return {"status": "triggered", "job_id": job_id}
    raise HTTPException(404, f"Job '{job_id}' not found")
