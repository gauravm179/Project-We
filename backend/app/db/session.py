from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        with engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))

    return engine


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine(), class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
