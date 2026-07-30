from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.brain.router import route_message
from app.web_learning.search import SearchResult


def test_route_coding_intent():
    decision = route_message("Write a Python function to reverse a list")
    assert decision.target == "coding-bot"


def test_route_web_search_intent():
    decision = route_message("search for Python PEP 8")
    assert decision.target == "web-learner-bot"


def test_route_explicit_voice_phrases():
    assert route_message("ask coding bot to explain recursion").target == "coding-bot"
    assert route_message("tell the web learner to capture this page").target == "web-learner-bot"
    assert route_message("ask the master bot what time it is").target == "master"


def test_route_current_affairs_to_web_learner():
    decision = route_message("show me current affairs")
    assert decision.target == "web-learner-bot"


def test_master_chat_routes_to_coding_bot(client: TestClient):
    resp = client.post("/chat", json={"message": "debug this Python stack trace please"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "coding-bot"
    assert "via" in data["response"].lower() or "You said:" in data["response"]


def test_voice_command_routes_to_coding_bot(client: TestClient):
    resp = client.post(
        "/voice/command",
        json={"transcript": "ask coding bot to write a unit test", "shared": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "coding-bot"
    assert data["reply"]


def test_voice_command_routes_web_search(
    client: TestClient, monkeypatch
):
    async def fake_search(self, query: str, *, limit: int = 5):
        return [
            SearchResult(title="PEP 8", url="https://example.com/pep8", snippet="style"),
        ]

    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)

    # Approve internet so web-learner can search
    created = client.post(
        "/permissions",
        json={"capability": "internet", "reason": "test"},
    ).json()
    client.post(f"/permissions/{created['id']}/decision", json={"approve": True})

    resp = client.post(
        "/voice/command",
        json={"transcript": "search for Python PEP 8", "shared": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "web-learner-bot"
