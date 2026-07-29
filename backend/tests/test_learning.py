from __future__ import annotations

from fastapi.testclient import TestClient


def test_coding_bot_learns_from_mistake_feedback(client: TestClient):
    resp = client.post(
        "/specialists/coding-bot/feedback",
        json={
            "mistake": "Said mutable default args are fine in Python",
            "correction": "Never use mutable default arguments; use None and create inside.",
            "language": "python",
            "topic": "defaults",
        },
    )
    assert resp.status_code == 201
    lesson = resp.json()
    assert lesson["specialist_slug"] == "coding-bot"
    assert "mutable" in lesson["mistake"]

    lessons = client.get("/specialists/coding-bot/lessons").json()
    assert any(item["id"] == lesson["id"] for item in lessons)

    chat = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "How should I write Python function defaults?"},
    )
    assert chat.status_code == 200
    data = chat.json()
    assert data["used_lessons"] is True
    assert "LESSONS FROM PAST MISTAKES" in data["response"] or "You said:" in data["response"]


def test_coding_bot_uses_local_guidelines_when_stuck(client: TestClient):
    chat = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "I'm stuck on Python best practice for imports"},
    )
    assert chat.status_code == 200
    data = chat.json()
    assert data["used_guidelines"] is True
    assert data["requires_permission"] is False


def test_coding_bot_asks_permission_for_live_internet_guidelines(client: TestClient):
    chat = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "Look up the latest online PEP 8 internet guidelines"},
    )
    assert chat.status_code == 200
    data = chat.json()
    assert data["requires_permission"] is True
    assert data["required_capability"] == "internet"
    assert data["permission_request_id"] is not None
    assert data["used_guidelines"] is True
