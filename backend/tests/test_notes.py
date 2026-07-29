from __future__ import annotations

from fastapi.testclient import TestClient


def test_agent_notes_api(client: TestClient):
    response = client.get("/notes")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Project We — Agent Notes"
    assert data["source"] == "docs/NOTES.md"
    assert "How bots work" in data["markdown"]
    assert data["browser_ui"] == "/ui/notes.html"


def test_agent_notes_raw(client: TestClient):
    response = client.get("/notes/raw")
    assert response.status_code == 200
    assert "Project We — Agent Notes" in response.text


def test_agent_notes_browser_page(client: TestClient):
    response = client.get("/ui/notes.html")
    assert response.status_code == 200
    assert "Agent Notes" in response.text
    assert "/notes" in response.text
