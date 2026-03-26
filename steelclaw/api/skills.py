"""REST API for skill management."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def list_skills(request: Request) -> list[dict]:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    skills = []
    for name, skill in registry.skills.items():
        skills.append({
            "name": name,
            "description": skill.metadata.description,
            "version": skill.metadata.version,
            "scope": skill.scope,
            "tools": [t.name for t in skill.tools],
            "triggers": skill.metadata.triggers,
        })
    return skills


@router.get("/{skill_name}")
async def get_skill(skill_name: str, request: Request) -> dict:
    from steelclaw.skills.registry import SkillRegistry

    registry: SkillRegistry = request.app.state.skill_registry
    skill = registry.get_skill(skill_name)
    if skill is None:
        from fastapi import HTTPException
        raise HTTPException(404, f"Skill '{skill_name}' not found")

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
