from __future__ import annotations

import time

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.brain.providers import build_provider
from app.brain.providers.ollama import OllamaProvider
from app.core.config import get_settings

router = APIRouter()

_OLLAMA_CACHE: dict[str, object] = {"at": 0.0, "info": None}
_OLLAMA_CACHE_SECONDS = 60.0


@router.get("/")
def root_redirect() -> RedirectResponse:
    """Send browsers to the Project We hub (not raw JSON)."""
    return RedirectResponse(url="/ui/home.html", status_code=307)


@router.get("/health")
async def health(
    probe: bool = Query(
        default=False,
        description="If true, ping Ollama now. Otherwise use a short cached check.",
    ),
) -> dict[str, object]:
    settings = get_settings()
    provider_info: dict[str, object] = {
        "provider": settings.provider,
        "model": settings.ollama_model if settings.provider == "ollama" else "echo",
        "chat_model": settings.ollama_chat_model if settings.provider == "ollama" else "echo",
        "tech_model": settings.ollama_tech_model if settings.provider == "ollama" else "echo",
        "auto_route_models": (
            settings.ollama_auto_route_models if settings.provider == "ollama" else False
        ),
        "reasoning": settings.ollama_reasoning if settings.provider == "ollama" else False,
    }

    if settings.provider == "ollama":
        now = time.monotonic()
        cached = _OLLAMA_CACHE.get("info")
        cache_at = float(_OLLAMA_CACHE.get("at") or 0.0)
        use_cache = (
            not probe
            and cached is not None
            and (now - cache_at) < _OLLAMA_CACHE_SECONDS
        )
        if use_cache and isinstance(cached, dict):
            provider_info.update(cached)
            provider_info["ollama_check"] = "cached"
        else:
            provider = build_provider(settings)
            if isinstance(provider, OllamaProvider):
                health_info = await provider.healthcheck()
                _OLLAMA_CACHE["at"] = now
                _OLLAMA_CACHE["info"] = health_info
                provider_info.update(health_info)
                provider_info["ollama_check"] = "live" if probe else "refreshed"

    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "sos_non_removable": True,
        "ai": provider_info,
        "home_ui": "/ui/home.html",
        "chat_ui": "/ui/",
        "voice_ui": "/ui/voice.html",
        "web_learner_ui": "/ui/web-learner.html",
        "notes_ui": "/ui/notes.html",
    }
