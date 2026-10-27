from __future__ import annotations

from fastapi import APIRouter

from firewing.inference.personas import load_personas

router = APIRouter(prefix="/v1/personas")


@router.get("")
def list_personas():
    personas = load_personas()
    return {
        "personas": [p.to_dict() for p in personas.values()]
    }


@router.get("/{name}")
def get_persona(name: str):
    personas = load_personas()
    if name not in personas:
        return {"error": f"Persona '{name}' not found"}, 404
    return personas[name].to_dict()
