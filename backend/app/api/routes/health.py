from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.brain.providers import build_provider
from app.brain.providers.ollama import OllamaProvider
from app.core.config import get_settings

router = APIRouter()


@router.get("/")
def root_redirect() -> RedirectResponse:
    """Send browsers to the coding-bot chat UI instead of raw JSON."""
    return RedirectResponse(url="/ui/", status_code=307)


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    provider_info: dict[str, object] = {
        "provider": settings.provider,
        "model": settings.ollama_model if settings.provider == "ollama" else "echo",
        "reasoning": settings.ollama_reasoning if settings.provider == "ollama" else False,
    }

    if settings.provider == "ollama":
        provider = build_provider(settings)
        if isinstance(provider, OllamaProvider):
            health_info = await provider.healthcheck()
            provider_info.update(health_info)

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "sos_non_removable": True,
        "ai": provider_info,
        "chat_ui": "/ui/",
        "web_learner_ui": "/ui/web-learner.html",
        "notes_ui": "/ui/notes.html",
    }
