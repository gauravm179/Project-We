from app.brain.providers.base import AIProvider
from app.brain.providers.echo import EchoProvider
from app.brain.providers.ollama import OllamaProvider
from app.core.config import Settings


def build_provider(settings: Settings, model_override: str | None = None) -> AIProvider:
    if settings.provider == "ollama":
        model = model_override or settings.ollama_model
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=model,
        )
    return EchoProvider()
