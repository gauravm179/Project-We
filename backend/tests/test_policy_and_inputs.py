def test_chat_requests_permission_for_internet_like_question(client):
    response = client.post("/chat", json={"message": "What is the latest weather today?"})
    assert response.status_code == 200
    body = response.json()
    assert body["requires_permission"] is True
    assert body["required_capability"] == "internet"
    assert isinstance(body["permission_request_id"], int)

    permissions = client.get("/permissions?status=pending")
    assert permissions.status_code == 200
    items = permissions.json()
    assert len(items) >= 1
    assert items[-1]["capability"] == "internet"
    assert items[-1]["status"] == "pending"


def test_screen_input_requires_explicit_share(client):
    denied = client.post(
        "/inputs/screen",
        json={"shared": False, "content": "Visible dashboard text", "source": "desktop"},
    )
    assert denied.status_code == 403

    accepted = client.post(
        "/inputs/screen",
        json={"shared": True, "content": "My name is Riya", "source": "desktop"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["input_type"] == "screen"

    memories = client.get("/memory")
    assert memories.status_code == 200
    assert any(
        item["memory_type"] == "fact"
        and item["key"] == "user_name"
        and item["value"] == "Riya"
        for item in memories.json()
    )


def test_voice_input_requires_explicit_share(client):
    denied = client.post(
        "/inputs/voice",
        json={"shared": False, "transcript": "Remind me to buy milk", "source": "mic"},
    )
    assert denied.status_code == 403

    accepted = client.post(
        "/inputs/voice",
        json={"shared": True, "transcript": "Remind me to buy milk", "source": "mic"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["input_type"] == "voice"

    summary = client.get("/memory/summary")
    assert summary.status_code == 200
    values = {item["memory_type"]: item["count"] for item in summary.json()}
    assert values.get("task", 0) >= 1
