from __future__ import annotations

from fastapi.testclient import TestClient


def _create_skill(client: TestClient, slug: str = "stock-analysis") -> dict:
    return client.post(
        "/skills",
        json={
            "slug": slug,
            "name": "Stock Analysis",
            "category": "trading",
            "description": "Analyze stock fundamentals and technicals",
            "instructions": (
                "When asked about a stock, analyze using P/E ratio, moving averages, "
                "and volume trends. Only use locally available data."
            ),
            "parameters_schema": {
                "ticker_symbols": {"type": "list", "description": "Symbols to track"},
                "analysis_depth": {"type": "string", "default": "standard"},
            },
        },
    ).json()


def _create_specialist(client: TestClient, slug: str = "trader") -> dict:
    return client.post(
        "/specialists",
        json={
            "slug": slug,
            "name": "Trader Bot",
            "sector": "trading",
            "system_prompt": "You are an expert trader.",
        },
    ).json()


def test_create_and_list_skills(client: TestClient):
    resp = client.post(
        "/skills",
        json={
            "slug": "debugging",
            "name": "Debugging",
            "category": "troubleshooting",
            "instructions": "Systematically debug issues using logs and traces.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "debugging"
    assert data["category"] == "troubleshooting"

    listing = client.get("/skills").json()
    assert any(s["slug"] == "debugging" for s in listing)


def test_get_skill_by_slug(client: TestClient):
    _create_skill(client)
    resp = client.get("/skills/stock-analysis")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "stock-analysis"


def test_skill_not_found(client: TestClient):
    resp = client.get("/skills/nonexistent")
    assert resp.status_code == 404


def test_duplicate_skill_rejected(client: TestClient):
    _create_skill(client)
    resp = client.post(
        "/skills",
        json={
            "slug": "stock-analysis",
            "name": "Duplicate",
            "category": "trading",
            "instructions": "dup",
        },
    )
    assert resp.status_code == 409


def test_specialist_learns_skill(client: TestClient):
    _create_skill(client)
    _create_specialist(client)

    resp = client.post(
        "/specialists/trader/skills",
        json={
            "skill_slug": "stock-analysis",
            "parameters": {"ticker_symbols": ["AAPL", "GOOG"], "analysis_depth": "deep"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["skill_slug"] == "stock-analysis"
    assert data["status"] == "learning"
    assert data["parameters"]["ticker_symbols"] == ["AAPL", "GOOG"]

    skills_list = client.get("/specialists/trader/skills").json()
    assert len(skills_list) == 1


def test_activate_learned_skill(client: TestClient):
    _create_skill(client)
    _create_specialist(client)

    learn_resp = client.post(
        "/specialists/trader/skills",
        json={"skill_slug": "stock-analysis", "parameters": {}},
    )
    assignment_id = learn_resp.json()["id"]

    resp = client.post(f"/skills/assignments/{assignment_id}/activate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["activated_at"] is not None


def test_update_assignment_parameters(client: TestClient):
    _create_skill(client)
    _create_specialist(client)

    learn_resp = client.post(
        "/specialists/trader/skills",
        json={"skill_slug": "stock-analysis", "parameters": {}},
    )
    assignment_id = learn_resp.json()["id"]

    resp = client.patch(
        f"/skills/assignments/{assignment_id}",
        json={"parameters": {"ticker_symbols": ["MSFT"]}, "status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["parameters"]["ticker_symbols"] == ["MSFT"]
    assert resp.json()["status"] == "active"


def test_active_skill_injected_into_chat(client: TestClient):
    _create_skill(client)
    _create_specialist(client)

    learn_resp = client.post(
        "/specialists/trader/skills",
        json={
            "skill_slug": "stock-analysis",
            "parameters": {"ticker_symbols": ["AAPL"]},
        },
    )
    assignment_id = learn_resp.json()["id"]
    client.post(f"/skills/assignments/{assignment_id}/activate")

    chat_resp = client.post(
        "/specialists/trader/chat",
        json={"message": "Analyze AAPL for me"},
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert "[specialist:" in data["response"]
    assert "LEARNED SKILLS" in data["response"]
    assert "Stock Analysis" in data["response"]


def test_learning_skill_not_injected_into_chat(client: TestClient):
    _create_skill(client)
    _create_specialist(client)

    client.post(
        "/specialists/trader/skills",
        json={"skill_slug": "stock-analysis", "parameters": {}},
    )

    chat_resp = client.post(
        "/specialists/trader/chat",
        json={"message": "What do you know?"},
    )
    assert chat_resp.status_code == 200
    assert "LEARNED SKILLS" not in chat_resp.json()["response"]


def test_global_skill_learn(client: TestClient):
    _create_skill(client, slug="general-debug")

    resp = client.post(
        "/skills/learn",
        json={"skill_slug": "general-debug", "parameters": {"verbose": True}},
    )
    assert resp.status_code == 201
    assert resp.json()["skill_slug"] == "general-debug"

    global_list = client.get("/skills/learned/global").json()
    slugs = {row["skill_slug"] for row in global_list}
    assert "general-debug" in slugs
    assert "store-local-learning" in slugs
    assert "recall-local-learning" in slugs
