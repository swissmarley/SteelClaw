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
