from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.policy.service import PolicyService
from app.web_learning.intent import extract_search_query
from app.web_learning.search import SearchResult


def test_permission_affirmations():
    policy = PolicyService()
    assert policy.parse_permission_reply("yes") is True
    assert policy.parse_permission_reply("yes approved") is True
    assert policy.parse_permission_reply("approved") is True
    assert policy.parse_permission_reply("Approve") is True
    assert policy.parse_permission_reply("ok") is True
    assert policy.parse_permission_reply("no") is False
    assert policy.parse_permission_reply("denied") is False
    assert policy.parse_permission_reply("write a python function") is None
    assert policy.parse_permission_reply("yes please explain trading charts") is None


def test_message_from_permission_reason():
    policy = PolicyService()
    reason = (
        "web-learner-bot needs web-learner-bot for: "
        "https://www.tradingview.com/chart/. Can you learn charts"
    )
    assert "tradingview.com" in (policy.message_from_permission_reason(reason) or "")


def test_learning_url_builds_search_query():
    q = extract_search_query(
        "https://www.tradingview.com/chart/. learn how to read trade charts"
    )
    assert q is not None
    assert "chart" in q.lower()


def test_chat_yes_approves_and_retries_web_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    html = (
        "<html><head><title>API Docs</title></head>"
        "<body><p>" + ("Dependency injection notes. " * 40) + "</p></body></html>"
    )

    class FakeResponse:
        def __init__(self, text: str = "", content: bytes = b"", content_type: str = "text/html"):
            self.text = text
            self.content = content
            self.headers = {"content-type": content_type}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            return FakeResponse(text=html)

    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Docs",
                url="https://example.com/api-docs",
                snippet="Official docs",
            )
        ]

    monkeypatch.setattr("app.web_learning.service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)

    # Non-chart URL ask still requires internet permission before capture.
    blocked = client.post(
        "/chat",
        json={"message": "Explain this page https://example.com/api-docs"},
    )
    assert blocked.status_code == 200
    body = blocked.json()
    assert body["requires_permission"] is True
    assert body["permission_request_id"] is not None
    assert "internet" in body["response"].lower()

    approved = client.post("/chat", json={"message": "yes approved"})
    assert approved.status_code == 200
    reply = approved.json()
    assert reply["requires_permission"] is False
    text = reply["response"].lower()
    assert "internet access approved" in text or "api" in text or "web learner" in text or "docs" in text

    pending = client.get("/permissions?status=pending").json()
    assert pending == []


def test_voice_yes_approves_pending_internet(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Docs",
                url="https://example.com/page",
                snippet="Useful page",
            )
        ]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            class FakeResponse:
                text = "<html><title>Guide</title><body>" + ("content " * 80) + "</body></html>"
                content = b""
                headers = {"content-type": "text/html"}

                def raise_for_status(self) -> None:
                    return None

            return FakeResponse()

    monkeypatch.setattr("app.web_learning.service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)

    blocked = client.post(
        "/voice/command",
        json={
            "transcript": "Read this page https://example.com/page",
            "shared": True,
            "speak": False,
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["requires_permission"] is True

    approved = client.post(
        "/voice/command",
        json={"transcript": "yes", "shared": True, "speak": False},
    )
    assert approved.status_code == 200
    data = approved.json()
    assert data.get("requires_permission") is False
    assert "approved" in data["reply"].lower() or "page" in data["reply"].lower() or "web" in data["reply"].lower()
