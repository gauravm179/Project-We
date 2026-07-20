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
    app_version: str = "0.3.0"
    provider: str = "echo"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3:8b"
    strict_local_mode: bool = True
    internet_mode: str = "ask"
    searxng_base_url: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        provider=os.getenv("PROJECT_WE_PROVIDER", "echo"),
        database_url=os.getenv("PROJECT_WE_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"),
        ollama_base_url=os.getenv("PROJECT_WE_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("PROJECT_WE_OLLAMA_MODEL", "llama3:8b"),
        strict_local_mode=os.getenv("PROJECT_WE_STRICT_LOCAL_MODE", "true").lower() == "true",
        internet_mode=os.getenv("PROJECT_WE_INTERNET_MODE", "ask").lower(),
        searxng_base_url=os.getenv("PROJECT_WE_SEARXNG_URL", ""),
    )
