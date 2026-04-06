"""REST API for agent management (CRUD + persona)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steelclaw.db.engine import get_async_session
from steelclaw.db.models import AgentProfile

router = APIRouter()


class AgentCreate(BaseModel):
    name: str
    display_name: str = ""
    system_prompt: str = ""
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    persona_json: Optional[str] = None
    parent_agent_id: Optional[str] = None


class AgentUpdate(BaseModel):
    display_name: Optional[str] = None
    system_prompt: Optional[str] = None
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    is_active: Optional[bool] = None
    parent_agent_id: Optional[str] = None


class PersonaUpdate(BaseModel):
    agent_name: Optional[str] = None
    user_name: Optional[str] = None
    tone: Optional[str] = None
    style: Optional[str] = None
    goals: Optional[list[str]] = None
    system_prompt_extension: Optional[str] = None


@router.get("")
async def list_agents(
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    stmt = select(AgentProfile).order_by(AgentProfile.created_at)
    result = await db.execute(stmt)
    return [_serialise(a) for a in result.scalars().all()]


@router.get("/{agent_id}/subagents")
async def list_subagents(
    agent_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> list[dict]:
    """Return all direct sub-agents of the given agent."""
    stmt = select(AgentProfile).where(
        AgentProfile.parent_agent_id == agent_id
    ).order_by(AgentProfile.created_at)
    result = await db.execute(stmt)
    return [_serialise(a) for a in result.scalars().all()]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _serialise(agent)


@router.post("")
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    # "main" is reserved for the system's main agent
    if body.name == "main":
        raise HTTPException(400, "The name 'main' is reserved for the system main agent")

    # Check for duplicate name
    existing = await db.execute(
        select(AgentProfile).where(AgentProfile.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Agent with name '{body.name}' already exists")

    # Validate parent agent if provided
    if body.parent_agent_id is not None:
        parent = await db.get(AgentProfile, body.parent_agent_id)
        if not parent:
            raise HTTPException(404, f"Parent agent '{body.parent_agent_id}' not found")

    agent = AgentProfile(
        name=body.name,
        display_name=body.display_name or body.name,
        system_prompt=body.system_prompt,
        model_override=body.model_override,
        temperature_override=body.temperature_override,
        persona_json=body.persona_json,
        is_main=False,
        parent_agent_id=body.parent_agent_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _serialise(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    if body.display_name is not None:
        agent.display_name = body.display_name
    if body.system_prompt is not None:
        agent.system_prompt = body.system_prompt
    if body.model_override is not None:
        agent.model_override = body.model_override
    if body.temperature_override is not None:
        agent.temperature_override = body.temperature_override
    if body.is_active is not None:
        agent.is_active = body.is_active
    if body.parent_agent_id is not None:
        # Validate parent exists and is not self-referential
        if body.parent_agent_id == agent_id:
            raise HTTPException(400, "An agent cannot be its own parent")
        parent = await db.get(AgentProfile, body.parent_agent_id)
        if not parent:
            raise HTTPException(404, f"Parent agent '{body.parent_agent_id}' not found")
        agent.parent_agent_id = body.parent_agent_id

    agent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _serialise(agent)


@router.put("/{agent_id}/persona")
async def update_persona(
    agent_id: str,
    body: PersonaUpdate,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Merge with existing persona
    existing = {}
    if agent.persona_json:
        try:
            existing = json.loads(agent.persona_json)
        except json.JSONDecodeError:
            pass

    updates = body.model_dump(exclude_none=True)
    existing.update(updates)
    agent.persona_json = json.dumps(existing)
    agent.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _serialise(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    agent = await db.get(AgentProfile, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if agent.is_main:
        raise HTTPException(400, "Cannot delete the main agent")

    await db.delete(agent)
    await db.commit()
    return {"status": "deleted", "agent_id": agent_id}


def _serialise(agent: AgentProfile) -> dict:
    persona = None
    if agent.persona_json:
        try:
            persona = json.loads(agent.persona_json)
        except json.JSONDecodeError:
            pass

    return {
        "id": agent.id,
        "name": agent.name,
        "display_name": agent.display_name,
        "is_main": agent.is_main,
        "system_prompt": agent.system_prompt,
        "persona": persona,
        "model_override": agent.model_override,
        "temperature_override": agent.temperature_override,
        "memory_namespace": agent.memory_namespace,
        "is_active": agent.is_active,
        "parent_agent_id": agent.parent_agent_id,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }
