def test_root_redirects_to_home_ui(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/home.html"


def test_root_opens_home_ui(client):
    response = client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert "Project We" in response.text
    assert "Voice Bot" in response.text


def test_chat_ui_alias(client):
    response = client.get("/chat-ui")
    assert response.status_code == 200
    assert "Code Assistant" in response.text


def test_ui_without_trailing_slash_redirects(client):
    response = client.get("/ui", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Project We"
    assert body["version"] == "0.3.1"
    assert body["status"] == "running"
    assert body["sos_non_removable"] is True
    assert body["ai"]["provider"] == "echo"
    assert body["ai"]["model"] == "echo"
    assert body["chat_ui"] == "/ui/"
    assert body["voice_ui"] == "/ui/voice.html"
    assert body["home_ui"] == "/ui/home.html"