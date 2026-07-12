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
    app_version: str = "0.1.0"
    provider: str = "echo"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        provider=os.getenv("PROJECT_WE_PROVIDER", "echo"),
        database_url=os.getenv("PROJECT_WE_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"),
        ollama_base_url=os.getenv("PROJECT_WE_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("PROJECT_WE_OLLAMA_MODEL", "qwen2.5:7b"),
    )
