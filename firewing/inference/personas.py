"""Persona / system-instruction presets.

A persona is just a named system prompt plus default sampling params.
Operators can add their own in configs/personas.yaml; FIREWING ships
sane defaults so `setup-ai chat` and the API work out of the box.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Persona:
    name: str
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_PERSONAS = {
    "default": Persona(
        name="default",
        system_prompt=(
            "You are FIREWING, a helpful AI assistant. Be direct, accurate, "
            "and concise. If you don't know something, say so."
        ),
        temperature=0.7,
        top_p=0.9,
    ),
    "coding": Persona(
        name="coding",
        system_prompt=(
            "You are FIREWING, an expert software engineer. Provide high-quality, "
            "correct, idiomatic code with clear explanations and minimal fluff."
        ),
        temperature=0.2,
        top_p=0.95,
    ),
    "concise": Persona(
        name="concise",
        system_prompt=(
            "You are FIREWING. Give strictly concise, factual, direct responses "
            "without introductory or concluding chatter."
        ),
        temperature=0.3,
        top_p=0.8,
    ),
    "creative": Persona(
        name="creative",
        system_prompt=(
            "You are FIREWING, an imaginative, expressive, and thoughtful assistant "
            "tailored for creative writing, storytelling, and brainstorming."
        ),
        temperature=0.85,
        top_p=0.95,
    ),
}

DEFAULT_PERSONA = DEFAULT_PERSONAS["default"]


def load_personas(path: str | None = None) -> dict[str, Persona]:
    personas = dict(DEFAULT_PERSONAS)
    target_path = Path(path) if path else Path("configs/personas.yaml")
    if not target_path.exists():
        target_path = Path("configs/personas.yml")
    if not target_path.exists():
        return personas

    try:
        import yaml

        raw = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
        for name, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            personas[name] = Persona(
                name=name,
                system_prompt=cfg.get("system_prompt", DEFAULT_PERSONA.system_prompt),
                temperature=float(cfg.get("temperature", DEFAULT_PERSONA.temperature)),
                top_p=float(cfg.get("top_p", DEFAULT_PERSONA.top_p)),
            )
    except Exception:
        pass

    return personas
