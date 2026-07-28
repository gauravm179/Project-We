from __future__ import annotations

from fastapi.testclient import TestClient


def _create_bot(client: TestClient, slug: str = "trading-bot", sector: str = "trading") -> dict:
    return client.post(
        "/specialists",
        json={
            "slug": slug,
            "name": f"{sector.title()} Bot",
            "sector": sector,
            "system_prompt": f"You are an expert in {sector}. Answer only about {sector}.",
            "description": f"Specialist for {sector}",
        },
    ).json()


def test_create_and_list(client: TestClient):
    resp = client.post(
        "/specialists",
        json={
            "slug": "trading-bot",
            "name": "Trading Bot",
            "sector": "trading",
            "system_prompt": "You are an expert trader.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "trading-bot"
    assert data["sector"] == "trading"
    assert data["enabled"] is True

    listing = client.get("/specialists").json()
    assert any(s["slug"] == "trading-bot" for s in listing)


def test_get_by_slug(client: TestClient):
    _create_bot(client)
    resp = client.get("/specialists/trading-bot")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "trading-bot"


def test_get_not_found(client: TestClient):
    resp = client.get("/specialists/nonexistent")
    assert resp.status_code == 404


def test_update(client: TestClient):
    _create_bot(client)
    resp = client.patch("/specialists/trading-bot", json={"name": "Updated Trader"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Trader"


def test_delete(client: TestClient):
    _create_bot(client)
    resp = client.delete("/specialists/trading-bot")
    assert resp.status_code == 204

    resp = client.get("/specialists/trading-bot")
    assert resp.status_code == 404


def test_chat_with_specialist(client: TestClient):
    _create_bot(client, slug="troubleshoot-bot", sector="troubleshooting")
    resp = client.post(
        "/specialists/troubleshoot-bot/chat",
        json={"message": "Why is my app crashing?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["specialist_slug"] == "troubleshoot-bot"
    assert data["specialist_name"] == "Troubleshooting Bot"
    assert "You said: Why is my app crashing?" in data["response"]
    assert "[specialist:" in data["response"]


def test_chat_not_found(client: TestClient):
    resp = client.post("/specialists/nope/chat", json={"message": "hi"})
    assert resp.status_code == 404


def test_chat_disabled_specialist(client: TestClient):
    _create_bot(client)
    client.patch("/specialists/trading-bot", json={"enabled": False})
    resp = client.post("/specialists/trading-bot/chat", json={"message": "hi"})
    assert resp.status_code == 404


def test_specialist_history(client: TestClient):
    _create_bot(client, slug="history-bot", sector="history")
    client.post("/specialists/history-bot/chat", json={"message": "Tell me about WW2"})

    resp = client.get("/specialists/history-bot/history")
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_multiple_specialists_isolated(client: TestClient):
    _create_bot(client, slug="alpha", sector="trading")
    _create_bot(client, slug="beta", sector="troubleshooting")

    client.post("/specialists/alpha/chat", json={"message": "Buy AAPL"})
    client.post("/specialists/beta/chat", json={"message": "Fix my server"})

    alpha_hist = client.get("/specialists/alpha/history").json()
    beta_hist = client.get("/specialists/beta/history").json()

    assert len(alpha_hist) == 2
    assert len(beta_hist) == 2
    assert "Buy AAPL" in alpha_hist[0]["content"]
    assert "Fix my server" in beta_hist[0]["content"]


def test_duplicate_slug_rejected(client: TestClient):
    _create_bot(client)
    resp = client.post(
        "/specialists",
        json={
            "slug": "trading-bot",
            "name": "Another",
            "sector": "trading",
            "system_prompt": "duplicate",
        },
    )
    assert resp.status_code == 409
