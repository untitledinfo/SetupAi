"""Persona / system-instruction presets.

A persona is just a named system prompt plus default sampling params.
Operators can add their own in configs/personas.yaml; FIREWING ships
one sane default so `setup-ai chat` works out of the box.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Persona:
    name: str
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9


DEFAULT_PERSONA = Persona(
    name="default",
    system_prompt=(
        "You are FIREWING, a helpful AI assistant. Be direct, accurate, "
        "and concise. If you don't know something, say so."
    ),
)


def load_personas(path: str | None = None) -> dict[str, Persona]:
    personas = {"default": DEFAULT_PERSONA}
    if not path:
        return personas
    import yaml
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return personas
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for name, cfg in raw.items():
        personas[name] = Persona(
            name=name,
            system_prompt=cfg.get("system_prompt", DEFAULT_PERSONA.system_prompt),
            temperature=cfg.get("temperature", DEFAULT_PERSONA.temperature),
            top_p=cfg.get("top_p", DEFAULT_PERSONA.top_p),
        )
    return personas
