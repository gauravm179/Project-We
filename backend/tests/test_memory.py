def test_memory_is_extracted_from_chat(client):
    response = client.post("/chat", json={"message": "My name is Gaurav"})
    assert response.status_code == 200

    memories = client.get("/memory")
    assert memories.status_code == 200
    items = memories.json()

    assert len(items) >= 1
    assert any(
        item["memory_type"] == "fact"
        and item["key"] == "user_name"
        and item["value"] == "Gaurav"
        for item in items
    )


def test_memory_summary(client):
    client.post("/chat", json={"message": "I use macOS"})
    client.post("/chat", json={"message": "Remind me to call mom"})

    summary_response = client.get("/memory/summary")
    assert summary_response.status_code == 200
    summary = {row["memory_type"]: row["count"] for row in summary_response.json()}

    assert summary.get("preference", 0) >= 1
    assert summary.get("task", 0) >= 1
