from __future__ import annotations

from fastapi.testclient import TestClient


def test_coding_bot_bootstrapped_on_startup(client: TestClient):
    specialists = client.get("/specialists").json()
    coding_bot = next((bot for bot in specialists if bot["slug"] == "coding-bot"), None)
    assert coding_bot is not None
    assert coding_bot["sector"] == "coding"
    assert coding_bot["enabled"] is True
    assert "software engineer" in coding_bot["system_prompt"].lower()


def test_coding_bot_has_trained_active_skills(client: TestClient):
    skills = client.get("/specialists/coding-bot/skills").json()
    skill_slugs = {skill["skill_slug"] for skill in skills}
    assert {
        "code-review",
        "write-tests",
        "debug-errors",
        "refactor-code",
        "build-logic",
    }.issubset(skill_slugs)
    assert {
        "store-local-learning",
        "recall-local-learning",
    }.issubset(skill_slugs)
    assert all(skill["status"] == "active" for skill in skills)


def test_coding_bot_uses_trained_skills_in_chat(client: TestClient):
    response = client.post(
        "/specialists/coding-bot/chat",
        json={"message": "Review this function for bugs"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["specialist_slug"] == "coding-bot"
    assert data["specialist_name"] == "Code Assistant"
    assert "LEARNED SKILLS" in data["response"]
    assert "Code Review" in data["response"]
