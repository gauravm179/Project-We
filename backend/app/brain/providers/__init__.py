from app.brain.providers.base import AIProvider
from app.brain.providers.echo import EchoProvider
from app.brain.providers.ollama import OllamaProvider
from app.core.config import Settings


def build_provider(settings: Settings) -> AIProvider:
    if settings.provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            chat_model=settings.ollama_chat_model,
            tech_model=settings.ollama_tech_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            reasoning=settings.ollama_reasoning,
            keep_alive=settings.ollama_keep_alive,
            num_predict=settings.ollama_num_predict,
            auto_route_models=settings.ollama_auto_route_models,
        )
    return EchoProvider()
