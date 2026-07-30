from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "project_we.db"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Project We"
    app_version: str = "0.3.3"
    provider: str = "echo"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_chat_model: str = "qwen2.5:1.5b"
    ollama_tech_model: str = "deepseek-r1:8b"
    ollama_timeout_seconds: float = 120.0
    ollama_temperature: float = 0.2
    ollama_reasoning: bool = True
    ollama_keep_alive: str = "30m"
    ollama_num_predict: int | None = None
    ollama_auto_route_models: bool = True
    strict_local_mode: bool = True
    internet_mode: str = "ask"
    web_search_engine: str = "duckduckgo"
    voice_enabled: bool = False
    voice_wake_word: str = "hey jarvis"
    voice_wake_sensitivity: float = 0.5
    voice_stt_model: str = "base"
    voice_tts_voice: str = "en_US-amy-medium"
    voice_silence_threshold: float = 1.5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        provider=os.getenv("PROJECT_WE_PROVIDER", "echo").lower(),
        database_url=os.getenv("PROJECT_WE_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"),
        ollama_base_url=os.getenv("PROJECT_WE_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("PROJECT_WE_OLLAMA_MODEL", "qwen2.5:1.5b"),
        ollama_chat_model=os.getenv(
            "PROJECT_WE_OLLAMA_CHAT_MODEL",
            os.getenv("PROJECT_WE_OLLAMA_MODEL", "qwen2.5:1.5b"),
        ),
        ollama_tech_model=os.getenv("PROJECT_WE_OLLAMA_TECH_MODEL", "deepseek-r1:8b"),
        ollama_timeout_seconds=float(os.getenv("PROJECT_WE_OLLAMA_TIMEOUT_SECONDS", "120")),
        ollama_temperature=float(os.getenv("PROJECT_WE_OLLAMA_TEMPERATURE", "0.2")),
        ollama_reasoning=os.getenv("PROJECT_WE_OLLAMA_REASONING", "true").lower() == "true",
        ollama_keep_alive=os.getenv("PROJECT_WE_OLLAMA_KEEP_ALIVE", "30m"),
        ollama_num_predict=(
            int(os.environ["PROJECT_WE_OLLAMA_NUM_PREDICT"])
            if os.getenv("PROJECT_WE_OLLAMA_NUM_PREDICT")
            else None
        ),
        ollama_auto_route_models=os.getenv(
            "PROJECT_WE_OLLAMA_AUTO_ROUTE_MODELS", "true"
        ).lower()
        == "true",
        strict_local_mode=os.getenv("PROJECT_WE_STRICT_LOCAL_MODE", "true").lower() == "true",
        internet_mode=os.getenv("PROJECT_WE_INTERNET_MODE", "ask").lower(),
        web_search_engine=os.getenv("PROJECT_WE_WEB_SEARCH_ENGINE", "duckduckgo").lower(),
        voice_enabled=os.getenv("PROJECT_WE_VOICE_ENABLED", "false").lower() == "true",
        voice_wake_word=os.getenv("PROJECT_WE_VOICE_WAKE_WORD", "hey jarvis"),
        voice_wake_sensitivity=float(os.getenv("PROJECT_WE_VOICE_WAKE_SENSITIVITY", "0.5")),
        voice_stt_model=os.getenv("PROJECT_WE_VOICE_STT_MODEL", "base"),
        voice_tts_voice=os.getenv("PROJECT_WE_VOICE_TTS_VOICE", "en_US-amy-medium"),
        voice_silence_threshold=float(os.getenv("PROJECT_WE_VOICE_SILENCE_THRESHOLD", "1.5")),
    )
