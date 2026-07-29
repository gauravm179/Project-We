from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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


def test_web_learner_bot_bootstrapped(client: TestClient):
    specialists = client.get("/specialists").json()
    bot = next((s for s in specialists if s["slug"] == "web-learner-bot"), None)
    assert bot is not None
    assert bot["sector"] == "web-learning"


def test_web_learner_has_trained_skills(client: TestClient):
    skills = client.get("/specialists/web-learner-bot/skills").json()
    slugs = {s["skill_slug"] for s in skills}
    assert slugs == {
        "read-web-page",
        "extract-page-images",
        "compress-store-learning",
        "recall-stored-pages",
    }
    assert all(s["status"] == "active" for s in skills)


def test_capture_requires_internet_permission(client: TestClient):
    resp = client.post(
        "/specialists/web-learner-bot/capture",
        json={"url": "https://example.com", "max_images": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requires_permission"] is True
    assert data["required_capability"] == "internet"


def test_capture_stores_compressed_learning(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    html = """
    <html><head><title>Example Learn</title></head>
    <body><h1>Hello Web</h1><p>Math lesson content</p>
    <img src="https://example.com/a.png" />
    </body></html>
    """

    class FakeResponse:
        def __init__(self, text: str = "", content: bytes = b"", content_type: str = "text/html"):
            self.text = text
            self.content = content
            self.headers = {"content-type": content_type}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            if url.endswith(".png"):
                return FakeResponse(content=b"fake-image-bytes", content_type="image/png")
            return FakeResponse(text=html)

    monkeypatch.setattr("app.web_learning.service.httpx.AsyncClient", FakeClient)
    _approve_internet(client)

    resp = client.post(
        "/specialists/web-learner-bot/capture",
        json={"url": "https://example.com/lesson", "max_images": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["capture_id"] >= 1
    assert data["title"] == "Example Learn"
    assert data["text_chars"] > 0
    assert data["compressed_bytes"] > 0

    listing = client.get("/specialists/web-learner-bot/captures").json()
    assert any(item["id"] == data["capture_id"] for item in listing)

    detail = client.get(f"/specialists/web-learner-bot/captures/{data['capture_id']}").json()
    assert "Hello Web" in detail["text"]
    assert detail["image_count"] >= 0


def test_web_learner_chat_uses_stored_learning(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    html = "<html><head><title>Stored</title></head><body><p>Stored page facts</p></body></html>"

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
            if str(url).endswith(".png"):
                return FakeResponse(content=b"x", content_type="image/png")
            return FakeResponse(text=html)

    monkeypatch.setattr("app.web_learning.service.httpx.AsyncClient", FakeClient)
    _approve_internet(client)
    client.post(
        "/specialists/web-learner-bot/capture",
        json={"url": "https://example.com/stored", "max_images": 0},
    )

    chat = client.post(
        "/specialists/web-learner-bot/chat",
        json={"message": "What did we learn from stored pages?"},
    )
    assert chat.status_code == 200
    body = chat.json()["response"]
    assert "STORED WEB LEARNING" in body or "You said:" in body
