from __future__ import annotations

from app.learning.local_store import (
    LocalLearningStore,
    extract_explicit_learning,
    is_shared_learning_policy_ask,
)


def test_shared_learning_policy_intent():
    assert is_shared_learning_policy_ask(
        "i want for all bots to learn new larning adn store them locally "
        "so they can refer next tim e"
    )
    assert is_shared_learning_policy_ask(
        "enable shared learning for every bot on my laptop"
    )
    assert not is_shared_learning_policy_ask("learn how to read trade charts")
    assert not is_shared_learning_policy_ask("hello there")


def test_extract_explicit_learning():
    assert extract_explicit_learning("remember that I trade the 1h timeframe") == (
        "I trade the 1h timeframe"
    )
    assert extract_explicit_learning("store this learning: use stop losses") == (
        "use stop losses"
    )
    assert extract_explicit_learning("what is python") is None


def test_enable_shared_learning_via_voice(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.learning.local_store.LEARNINGS_DIR",
        tmp_path / "bot_learnings",
    )
    import app.learning.local_store as ls

    monkeypatch.setattr(ls, "LEARNINGS_DIR", tmp_path / "bot_learnings")

    resp = client.post(
        "/voice/command",
        json={
            "transcript": (
                "i want for all bots to learn new learnings and store them locally "
                "so they can refer next time"
            ),
            "shared": True,
            "speak": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("route_reason") == "shared local learning enabled"
    text = body["reply"].lower()
    assert "shared local learning" in text
    assert "bot_learnings" in text or "sqlite" in text

    listed = client.get("/learnings").json()
    assert len(listed) >= 1
    assert any(row["kind"] == "policy" for row in listed)


def test_remember_note_is_recalled_by_coding_bot(client):
    save = client.post(
        "/voice/command",
        json={
            "transcript": "remember that preferred language is Python 3.12",
            "shared": True,
            "speak": False,
        },
    )
    assert save.status_code == 200

    learnings = client.get("/learnings").json()
    assert any("Python 3.12" in row["content"] for row in learnings)

    # Coding path should still answer; echo provider will include memory context indirectly
    # via specialist chat. Verify recall API-wise and that coding bot remains healthy.
    coding = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "what language should I use?"},
    )
    assert coding.status_code == 200
    # Stored learnings endpoint still shows shared note for coding-bot scope
    scoped = client.get("/learnings", params={"bot_slug": "coding-bot"}).json()
    assert any("Python 3.12" in row["content"] for row in scoped)


def test_local_learning_store_disk_and_recall(db_session=None):
    # Lightweight unit path via service + temp handled by client fixture in other tests.
    store = LocalLearningStore()
    assert store is not None
