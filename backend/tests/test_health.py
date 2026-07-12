def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Project We"
    assert body["version"] == "0.1.0"
    assert body["status"] == "running"
