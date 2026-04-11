"""REST API for Claude-compatible skills management (Phase 2).

This module manages the NEW Skills system — self-contained instruction bundles
that provide context to the agent without executable tool functions. These are
separate from the Tools system (formerly Skills, renamed in Phase 1).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

router = APIRouter()


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    triggers: list[str] = []
    system_prompt: str = ""
    scope: str = "global"


class SkillGenerate(BaseModel):
    description: str


# ── List & Detail ────────────────────────────────────────────────────────────


@router.get("")
async def list_skills(request: Request) -> list[dict]:
    """List all discovered skills with status."""
    manager = _get_manager(request)
    active = set(manager.skills.keys())
    result = []
    for name, skill in manager.all_skills.items():
        result.append({
            "name": name,
            "description": skill.metadata.description,
            "version": skill.metadata.version,
            "author": skill.metadata.author,
            "scope": skill.scope,
            "triggers": skill.metadata.triggers,
            "enabled": name in active,
            "has_system_prompt": bool(skill.metadata.system_prompt),
            "has_tools": len(skill.tools) > 0,
            "path": str(skill.path),
        })
    return result


@router.get("/{skill_name}")
async def get_skill(skill_name: str, request: Request) -> dict:
    """Get detailed information about a single skill."""
    manager = _get_manager(request)
    skill = manager.get_all_skill(skill_name)
    if skill is None:
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    active = set(manager.skills.keys())
    skill_md_path = skill.path / "SKILL.md"
    raw_content = ""
    if skill_md_path.exists():
        raw_content = skill_md_path.read_text(encoding="utf-8")

    return {
        "name": skill.name,
        "description": skill.metadata.description,
        "version": skill.metadata.version,
        "author": skill.metadata.author,
        "scope": skill.scope,
        "system_prompt": skill.metadata.system_prompt,
        "triggers": skill.metadata.triggers,
        "tools": [t.to_openai_tool() for t in skill.tools],
        "path": str(skill.path),
        "enabled": skill.name in active,
        "raw_content": raw_content,
    }


# ── Create & Delete ──────────────────────────────────────────────────────────


@router.post("")
async def create_skill(body: SkillCreate, request: Request) -> dict:
    """Create a new skill from parameters."""
    manager = _get_manager(request)
    try:
        skill = manager.create_skill(
            name=body.name,
            description=body.description,
            version=body.version,
            author=body.author,
            triggers=body.triggers,
            system_prompt=body.system_prompt,
            scope=body.scope,
        )
        return {"status": "created", "skill": skill.name}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str, request: Request) -> dict:
    """Delete a skill."""
    manager = _get_manager(request)
    if not manager.delete_skill(skill_name):
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    _persist_skill_toggle(skill_name, enable=None)
    return {"status": "deleted", "skill": skill_name}


# ── Enable / Disable ──────────────────────────────────────────────────────────


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str, request: Request) -> dict:
    """Enable a skill."""
    manager = _get_manager(request)
    if not manager.enable_skill(skill_name):
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    _persist_skill_toggle(skill_name, enable=True)
    return {"status": "enabled", "skill": skill_name}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str, request: Request) -> dict:
    """Disable a skill."""
    manager = _get_manager(request)
    if not manager.disable_skill(skill_name):
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    _persist_skill_toggle(skill_name, enable=False)
    return {"status": "disabled", "skill": skill_name}


# ── Import / Export ───────────────────────────────────────────────────────────


@router.post("/import")
async def import_skill(
    request: Request,
    file: UploadFile = File(None),
    scope: str = "global",
) -> dict:
    """Import a skill from an uploaded file (.md, .zip)."""
    manager = _get_manager(request)

    if file is None or not file.filename:
        raise HTTPException(400, "No file provided")

    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        skill = manager.import_skill(tmp_path, scope=scope)
        return {"status": "imported", "skill": skill.name}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/import-path")
async def import_skill_from_path(request: Request) -> dict:
    """Import a skill from a local filesystem path."""
    body = await request.json()
    path = body.get("path")
    scope = body.get("scope", "global")

    if not path:
        raise HTTPException(400, "Missing 'path' field")

    manager = _get_manager(request)
    try:
        skill = manager.import_skill(Path(path), scope=scope)
        return {"status": "imported", "skill": skill.name}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, f"Path not found: {path}")


@router.get("/{skill_name}/export")
async def export_skill(skill_name: str, request: Request) -> dict:
    """Export a skill as a zip archive."""
    manager = _get_manager(request)
    try:
        zip_path = manager.export_skill(skill_name)
        return {
            "status": "exported",
            "skill": skill_name,
            "path": str(zip_path),
            "filename": f"{skill_name}.zip",
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Generate ──────────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_skill(body: SkillGenerate, request: Request) -> dict:
    """Generate a new skill from a natural language description."""
    manager = _get_manager(request)

    # Try LLM-based generation
    llm_provider = getattr(request.app.state, "llm_provider", None)
    if llm_provider is None:
        try:
            from steelclaw.llm.provider import LLMProvider
            settings = request.app.state.settings
            llm_provider = LLMProvider(settings.agents.llm)
        except Exception:
            llm_provider = None

    if llm_provider is not None:
        try:
            skill = await manager.generate_skill_async(body.description, llm_provider)
            return {"status": "generated", "skill": skill.name}
        except Exception:
            pass

    # Fallback: template-based generation
    try:
        skill = manager.generate_skill(body.description)
        return {"status": "generated", "skill": skill.name}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Reload & Test ────────────────────────────────────────────────────────────


@router.post("/reload")
async def reload_skills(request: Request) -> dict:
    """Reload all skills from disk."""
    manager = _get_manager(request)
    manager.load_all()
    return {"status": "reloaded", "count": len(manager.skills)}


@router.post("/test")
async def test_skill_trigger(request: Request) -> dict:
    """Test trigger matching against a message."""
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "Missing 'message' field")

    manager = _get_manager(request)
    matched = manager.find_skills_by_trigger(message)
    return {
        "message": message,
        "matched_skills": [
            {
                "name": s.name,
                "description": s.metadata.description,
                "version": s.metadata.version,
                "matched_triggers": [
                    t for t in s.metadata.triggers if t.lower() in message.lower()
                ],
            }
            for s in matched
        ],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_manager(request: Request):
    """Get the SkillManager from app state."""
    manager = getattr(request.app.state, "skill_manager", None)
    if manager is None:
        raise HTTPException(500, "Skill manager not initialized")
    return manager


def _persist_skill_toggle(name: str, enable: Optional[bool]) -> None:
    """Save skill enable/disable state to config.json."""
    from steelclaw.api.config import _read_config, _write_config

    cfg = _read_config()
    skills = cfg.setdefault("agents", {}).setdefault("skills", {})
    disabled = skills.setdefault("disabled_skills", [])
    enabled = skills.setdefault("enabled_skills", [])

    if enable is True:
        if name in disabled:
            disabled.remove(name)
        if name not in enabled:
            enabled.append(name)
    elif enable is False:
        if name in enabled:
            enabled.remove(name)
        if name not in disabled:
            disabled.append(name)
    elif enable is None:
        # Remove from both (skill deleted)
        disabled[:] = [n for n in disabled if n != name]
        enabled[:] = [n for n in enabled if n != name]

    _write_config(cfg)