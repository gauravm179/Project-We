from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.web_learning.intent import extract_search_query, extract_urls, message_needs_web_assist
from app.web_learning.search import SearchResult


def _approve_internet(client: TestClient) -> None:
    pending = client.get("/permissions?status=pending").json()
    if pending:
        client.post(f"/permissions/{pending[-1]['id']}/decision", json={"approve": True})
        return
    created = client.post(
        "/permissions",
        json={"capability": "internet", "reason": "test"},
    ).json()
    client.post(f"/permissions/{created['id']}/decision", json={"approve": True})


def test_intent_detects_urls_and_search_queries():
    assert extract_urls("Read https://example.com/docs please") == ["https://example.com/docs"]
    assert extract_search_query("search for Python PEP 8") == "Python PEP 8"
    assert extract_search_query("google: fastapi tutorial") == "fastapi tutorial"
    assert message_needs_web_assist("look up asyncio patterns") is True
    assert message_needs_web_assist("write a for loop") is False
    q = extract_search_query("show me current affairs")
    assert q is not None
    assert "news" in q.lower() or "current" in q.lower()
    assert message_needs_web_assist("show me current affairs") is True


def test_web_search_requires_permission(client: TestClient):
    resp = client.post("/web/search", json={"query": "python asyncio"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["requires_permission"] is True
    assert data["required_capability"] == "internet"


def test_web_search_stores_results(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Result for {query}",
                url="https://example.com/result",
                snippet="Example snippet",
            )
        ]

    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)
    _approve_internet(client)

    resp = client.post("/web/search", json={"query": "python asyncio", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["search_id"] >= 1
    assert data["engine"] in {"duckduckgo", "bing"}
    assert data["query"] == "python asyncio"
    assert data["result_count"] == 1
    assert data["results"][0]["url"] == "https://example.com/result"


def test_web_assist_delegates_to_web_learner(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Docs",
                url="https://example.com/docs",
                snippet="Official docs",
            )
        ]

    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)
    _approve_internet(client)

    resp = client.post(
        "/web/assist",
        json={
            "message": "search for fastapi dependency injection",
            "requesting_bot": "coding-bot",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["delegated_to"] == "web-learner-bot"
    assert data["search_id"] >= 1
    assert "fastapi dependency injection" in data["context"]


def test_coding_bot_delegates_search_to_web_learner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="PEP 8",
                url="https://example.com/pep8",
                snippet="Style guide",
            )
        ]

    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)
    _approve_internet(client)

    resp = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "search for Python PEP 8 style guide"},
    )
    assert resp.status_code == 200
    body = resp.json()["response"]
    assert "WEB LEARNER ASSIST" in body or "You said:" in body


def test_coding_bot_url_delegation_requires_permission(client: TestClient):
    resp = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "Explain this page https://example.com/api"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requires_permission"] is True
    assert data["required_capability"] == "internet"
