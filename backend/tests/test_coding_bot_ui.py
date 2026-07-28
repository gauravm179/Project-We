from __future__ import annotations

from fastapi.testclient import TestClient


def test_coding_bot_capabilities_endpoint(client: TestClient):
    response = client.get("/specialists/coding-bot/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "coding-bot"
    assert data["browser_ui"] == "/ui/"
    assert len(data["languages"]) >= 10
    assert "python" in {lang["id"] for lang in data["languages"]}
    assert len(data["logic_capabilities"]) >= 3
    assert len(data["build_capabilities"]) >= 3
    assert "build-logic" in data["trained_skills"]


def test_local_browser_ui_is_served(client: TestClient):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "Code Assistant" in response.text
    assert "coding-bot" in response.text
