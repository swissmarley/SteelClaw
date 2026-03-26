"""Health and info endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from steelclaw import __version__

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/info")
async def info(request: Request) -> dict:
    from steelclaw.gateway.registry import ConnectorRegistry

    registry: ConnectorRegistry = request.app.state.registry
    connectors = {}
    for name, connector in registry.active_connectors.items():
        task = connector._task
        if task is None:
            status = "stopped"
        elif task.done():
            status = "exited"
        else:
            status = "running"
        connectors[name] = status

    return {
        "version": __version__,
        "connectors": connectors,
    }
