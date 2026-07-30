def test_chat_round_trip(client):
    response = client.post("/chat", json={"message": "Hello Project We"})
    assert response.status_code == 200
    text = response.json()["response"]
    assert text.startswith("You said: Hello Project We")


def test_chat_history(client):
    client.post("/chat", json={"message": "First"})
    client.post("/chat", json={"message": "Second"})

    history_response = client.get("/chat/history?limit=10")
    assert history_response.status_code == 200
    items = history_response.json()

    assert len(items) >= 4
    assert items[-2]["role"] == "user"
    assert items[-2]["content"] == "Second"
    assert items[-1]["role"] == "assistant"
    assert items[-1]["content"].startswith("You said: Second")
