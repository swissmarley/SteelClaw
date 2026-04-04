"""REST API for live configuration management — powers the Control UI."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

from steelclaw.paths import PROJECT_ROOT

CONFIG_PATH = PROJECT_ROOT / "config.json"


def _read_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def _write_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Full config ─────────────────────────────────────────────────────────


@router.get("")
async def get_config(request: Request) -> dict:
    """Return current running configuration (secrets masked)."""
    settings = request.app.state.settings
    data = _read_config()
    # Mask API keys in response
    return _mask_secrets(data)


@router.put("")
async def update_config(request: Request) -> dict:
    """Replace the entire config.json. Requires server restart for changes to take effect."""
    body = await request.json()
    _write_config(body)
    return {"status": "saved", "note": "Restart the server for changes to take effect."}


# ── Section-level endpoints ─────────────────────────────────────────────


@router.get("/llm")
async def get_llm_config(request: Request) -> dict:
    data = _read_config()
    llm = data.get("agents", {}).get("llm", {})
    return _mask_secrets({"llm": llm})


@router.put("/llm")
async def update_llm_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("agents", {})["llm"] = body
    _write_config(data)
    return {"status": "saved", "section": "llm"}


@router.get("/gateway")
async def get_gateway_config(request: Request) -> dict:
    data = _read_config()
    gw = data.get("gateway", {})
    return _mask_secrets({"gateway": gw})


@router.put("/gateway")
async def update_gateway_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data["gateway"] = body
    _write_config(data)
    return {"status": "saved", "section": "gateway"}


@router.get("/security")
async def get_security_config(request: Request) -> dict:
    data = _read_config()
    sec = data.get("agents", {}).get("security", {})
    return {"security": sec}


@router.put("/security")
async def update_security_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("agents", {})["security"] = body
    _write_config(data)
    return {"status": "saved", "section": "security"}


@router.get("/server")
async def get_server_config(request: Request) -> dict:
    data = _read_config()
    return {"server": data.get("server", {})}


@router.put("/server")
async def update_server_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data["server"] = body
    _write_config(data)
    return {"status": "saved", "section": "server"}


@router.get("/database")
async def get_database_config(request: Request) -> dict:
    data = _read_config()
    return {"database": data.get("database", {})}


@router.put("/database")
async def update_database_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data["database"] = body
    _write_config(data)
    return {"status": "saved", "section": "database"}


@router.get("/voice")
async def get_voice_config(request: Request) -> dict:
    data = _read_config()
    voice = data.get("agents", {}).get("voice", {})
    return {"voice": voice}


@router.put("/voice")
async def update_voice_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("agents", {})["voice"] = body
    _write_config(data)
    return {"status": "saved", "section": "voice"}


@router.get("/skills")
async def get_skills_config(request: Request) -> dict:
    data = _read_config()
    skills = data.get("agents", {}).get("skills", {})
    return {"skills": skills}


@router.put("/skills")
async def update_skills_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("agents", {})["skills"] = body
    _write_config(data)
    return {"status": "saved", "section": "skills"}


@router.get("/scheduler")
async def get_scheduler_config(request: Request) -> dict:
    data = _read_config()
    sched = data.get("agents", {}).get("scheduler", {})
    return {"scheduler": sched}


@router.put("/scheduler")
async def update_scheduler_config(request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("agents", {})["scheduler"] = body
    _write_config(data)
    return {"status": "saved", "section": "scheduler"}


@router.put("/connectors/{platform}")
async def update_connector_config(platform: str, request: Request) -> dict:
    body = await request.json()
    data = _read_config()
    data.setdefault("gateway", {}).setdefault("connectors", {})[platform] = body
    _write_config(data)

    from steelclaw.gateway.registry import ConnectorRegistry
    from steelclaw.settings import ConnectorConfig

    registry: ConnectorRegistry = request.app.state.registry

    if body.get("enabled"):
        try:
            conf = ConnectorConfig.model_validate(body)
        except Exception:
            conf = ConnectorConfig(enabled=True, token=body.get("token"))
        connector, error = await registry.start_connector(platform, conf)
        if error:
            return {"status": "error", "message": error, "section": f"connectors.{platform}"}
        return {"status": "running", "section": f"connectors.{platform}"}
    else:
        await registry.stop_connector(platform)
        return {"status": "disabled", "section": f"connectors.{platform}"}


@router.get("/connectors")
async def get_connectors_status(request: Request) -> dict:
    """Return connector config + live status."""
    from steelclaw.gateway.registry import ConnectorRegistry

    registry: ConnectorRegistry = request.app.state.registry
    data = _read_config()
    connectors_cfg = data.get("gateway", {}).get("connectors", {})

    result = {}
    for name, cfg in connectors_cfg.items():
        connector = registry.get(name)
        if connector and connector._task and not connector._task.done():
            status = "running"
        elif cfg.get("enabled"):
            status = "enabled_not_running"
        else:
            status = "disabled"
        entry = {
            "enabled": cfg.get("enabled", False),
            "status": status,
            "config": _mask_secrets(cfg),
        }
        if connector and connector.last_error:
            entry["last_error"] = connector.last_error
        result[name] = entry
    return {"connectors": result}


@router.get("/approvals")
async def get_approvals(request: Request) -> dict:
    pm = request.app.state.permission_manager
    return {"rules": pm.approvals.list_rules()}


@router.post("/approvals")
async def add_approval(request: Request) -> dict:
    body = await request.json()
    pm = request.app.state.permission_manager
    pm.approvals.add_rule(
        pattern=body["pattern"],
        permission=body.get("permission", "ignore"),
        note=body.get("note", ""),
    )
    return {"status": "added"}


@router.delete("/approvals/{pattern:path}")
async def remove_approval(pattern: str, request: Request) -> dict:
    pm = request.app.state.permission_manager
    if pm.approvals.remove_rule(pattern):
        return {"status": "removed"}
    raise HTTPException(404, "Rule not found")


# ── Helpers ─────────────────────────────────────────────────────────────


def _mask_secrets(data: dict) -> dict:
    """Recursively mask values whose keys look like secrets."""
    secret_keys = {"token", "api_key", "password", "secret", "signing_secret", "app_password"}
    masked = {}
    for k, v in data.items():
        if isinstance(v, dict):
            masked[k] = _mask_secrets(v)
        elif k.lower() in secret_keys and isinstance(v, str) and len(v) > 8:
            masked[k] = v[:4] + "****" + v[-4:]
        else:
            masked[k] = v
    return masked
