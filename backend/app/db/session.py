from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


def _session_local():
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine(), class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = _session_local()()
    try:
        yield db
    finally:
        db.close()
