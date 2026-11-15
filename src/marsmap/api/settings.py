"""Configuración de la API desde variables de entorno (ver .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("DATA_DIR", "data/processed"))
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get(
                "CORS_ORIGINS", "http://localhost:5173,http://localhost:5174,http://localhost:3000"
            ).split(",")
            if o.strip()
        )
    )
    rate_limit_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 30))
    mission_rate_limit_per_minute: int = field(
        default_factory=lambda: _int("MISSION_RATE_LIMIT_PER_MINUTE", 5)
    )
    compute_timeout_s: float = field(
        default_factory=lambda: float(_int("COMPUTE_TIMEOUT_SECONDS", 10))
    )
    # IA del hábitat (018): Groq, API compatible con OpenAI. Sin clave, el endpoint responde 503.
    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", "").strip())
    groq_model: str = field(
        default_factory=lambda: os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    )
    groq_timeout_s: float = field(default_factory=lambda: float(_int("GROQ_TIMEOUT_SECONDS", 20)))
    chat_rate_limit_per_minute: int = field(
        default_factory=lambda: _int("CHAT_RATE_LIMIT_PER_MINUTE", 12)
    )
    frontend_dist: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["FRONTEND_DIST"]) if os.environ.get("FRONTEND_DIST") else None
        )
    )
