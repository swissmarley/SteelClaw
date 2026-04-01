"""REST API for persona management."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from steelclaw.agents.persona_loader import load_persona, save_persona

router = APIRouter()


class PersonaData(BaseModel):
    agent_name: str = "SteelClaw"
    user_name: str = ""
    personality_description: str = ""
    tone: str = "friendly"
    goals: list[str] = []
    additional_prompts: str = ""


@router.get("")
async def get_persona() -> dict:
    """Return current persona configuration."""
    return load_persona()


@router.post("")
async def update_persona(data: PersonaData) -> dict:
    """Update persona configuration."""
    persona = data.model_dump()
    save_persona(persona)
    return {"status": "saved", "persona": persona}
