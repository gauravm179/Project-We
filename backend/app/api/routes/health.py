from __future__ import annotations

from fastapi import APIRouter

from app.brain.providers import build_provider
from app.brain.providers.ollama import OllamaProvider
from app.core.config import get_settings

router = APIRouter()


@router.get("/")
async def root() -> dict[str, object]:
    settings = get_settings()
    provider_info: dict[str, object] = {
        "provider": settings.provider,
        "model": settings.ollama_model if settings.provider == "ollama" else "echo",
        "reasoning": settings.ollama_reasoning if settings.provider == "ollama" else False,
    }

    if settings.provider == "ollama":
        provider = build_provider(settings)
        if isinstance(provider, OllamaProvider):
            health = await provider.healthcheck()
            provider_info.update(health)

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "sos_non_removable": True,
        "ai": provider_info,
    }
