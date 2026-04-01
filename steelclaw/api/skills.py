"""REST API for skill management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class CredentialUpdate(BaseModel):
    credentials: dict[str, str]


@router.get("")
async def list_skills(request: Request) -> list[dict]:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    active_skills = set(registry.skills.keys())
    skills = []
    for name, skill in registry.all_skills.items():
        skills.append({
            "name": name,
            "description": skill.metadata.description,
            "version": skill.metadata.version,
            "scope": skill.scope,
            "tools": [t.name for t in skill.tools],
            "triggers": skill.metadata.triggers,
            "enabled": name in active_skills,
            "default_enabled": skill.default_enabled,
            "required_credentials": skill.required_credentials,
        })
    return skills


@router.get("/{skill_name}/credentials")
async def get_skill_credentials(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    creds = registry.get_skill_credentials(skill_name)
    if creds is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    return {"skill": skill_name, "credentials": creds}


@router.put("/{skill_name}/credentials")
async def update_skill_credentials(
    skill_name: str, body: CredentialUpdate, request: Request
) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    if not registry.set_skill_credentials(skill_name, body.credentials):
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    # Persist to config.json
    from steelclaw.api.config import _read_config, _write_config

    settings = request.app.state.settings
    cfg = _read_config()
    skill_configs = cfg.setdefault("agents", {}).setdefault("skills", {}).setdefault("skill_configs", {})
    skill_configs[skill_name] = settings.agents.skills.skill_configs.get(skill_name, {})
    _write_config(cfg)
    return {"status": "saved", "skill": skill_name}


class CredentialVerify(BaseModel):
    credential: str
    value: str


@router.post("/{skill_name}/verify")
async def verify_skill_credentials(skill_name: str, body: CredentialVerify, request: Request) -> dict:
    import httpx
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    skill = registry.all_skills.get(skill_name)
    if skill is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    # Find the requested credential spec
    cred_spec = None
    for cred in skill.required_credentials:
        if cred["key"] == body.credential:
            cred_spec = cred
            break

    if cred_spec is None:
        return {"valid": False, "message": f"Unknown credential '{body.credential}'"}

    # Use the value from the request (allows verify before save)
    value = body.value
    if not value:
        # Fall back to stored value
        stored = request.app.state.settings.agents.skills.skill_configs.get(skill_name, {})
        value = stored.get(body.credential, "")

    if not value:
        return {"valid": False, "message": "Not set"}

    test_url = cred_spec.get("test_url")
    if not test_url:
        return {"valid": True, "message": "Value provided (no test URL available)"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                test_url,
                headers={"Authorization": f"Bearer {value}"},
            )
            if resp.status_code < 400:
                return {"valid": True, "message": f"OK ({resp.status_code})"}
            elif resp.status_code == 401:
                return {"valid": False, "message": "Invalid API key (401)"}
            else:
                return {"valid": False, "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "message": str(e)}


@router.get("/{skill_name}")
async def get_skill(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    skill = registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    disabled = set(registry.disabled_skills)
    return {
        "name": skill.name,
        "description": skill.metadata.description,
        "version": skill.metadata.version,
        "author": skill.metadata.author,
        "scope": skill.scope,
        "system_prompt": skill.metadata.system_prompt,
        "tools": [t.to_openai_tool() for t in skill.tools],
        "triggers": skill.metadata.triggers,
        "path": str(skill.path),
        "enabled": skill.name not in disabled,
        "required_credentials": skill.required_credentials,
    }


@router.get("/tools/all")
async def list_all_tools(request: Request) -> list[dict]:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    return registry.get_all_tools_schema()


@router.post("/reload")
async def reload_skills(request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    registry.load_all()
    return {"status": "reloaded", "count": len(registry.skills)}


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    if not registry.enable_skill(skill_name):
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    _persist_skill_toggle(skill_name, enable=True)
    return {"status": "enabled", "skill": skill_name}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    if not registry.disable_skill(skill_name):
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    _persist_skill_toggle(skill_name, enable=False)
    return {"status": "disabled", "skill": skill_name}


def _persist_skill_toggle(name: str, enable: bool) -> None:
    """Save skill enable/disable state to config.json so it survives restarts."""
    from steelclaw.api.config import _read_config, _write_config

    cfg = _read_config()
    skills = cfg.setdefault("agents", {}).setdefault("skills", {})
    disabled = skills.setdefault("disabled_skills", [])
    enabled = skills.setdefault("enabled_skills", [])

    if enable:
        if name in disabled:
            disabled.remove(name)
        if name not in enabled:
            enabled.append(name)
    else:
        if name in enabled:
            enabled.remove(name)
        if name not in disabled:
            disabled.append(name)

    _write_config(cfg)
