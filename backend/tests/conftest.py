from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "project_we_test.db"
    monkeypatch.setenv("PROJECT_WE_DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("PROJECT_WE_PROVIDER", "echo")

    from app.core.config import get_settings
    from app.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
