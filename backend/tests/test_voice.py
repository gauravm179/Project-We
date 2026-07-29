from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_voice_status_available(client: TestClient):
    response = client.get("/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert "wake_word" in data
    assert "deps_ready" in data
    assert data["active"] is False


def test_voice_start_fails_without_deps(client: TestClient):
    with patch("app.voice.assistant.VoiceAssistant._check_deps_ready", return_value=False):
        response = client.post("/voice/start")
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "wake-word" in detail or "pip install" in detail
        # Browser path must still be healthy
        status = client.get("/voice/status").json()
        assert status["active"] is False
        assert status["deps_ready"] is False
        # Sticky scary error should not block the UI status
        assert not (status.get("last_error") or "").lower().startswith("voice hardware")

def test_voice_start_and_stop_routes(client: TestClient):
    with patch("app.api.routes.voice.voice_assistant.start", new_callable=AsyncMock) as mock_start:
        response = client.post("/voice/start")
        assert response.status_code == 200
        mock_start.assert_called_once()

    with patch("app.api.routes.voice.voice_assistant.stop", new_callable=AsyncMock) as mock_stop:
        response = client.post("/voice/stop")
        assert response.status_code == 200
        mock_stop.assert_called_once()


def test_voice_config_patch(client: TestClient):
    response = client.patch(
        "/voice/config",
        json={
            "wake_word": "hey jarvis",
            "wake_sensitivity": 0.6,
            "stt_model": "small",
            "tts_voice": "en_US-amy-medium",
            "silence_threshold": 2.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["wake_word"] == "hey jarvis"
    assert data["wake_sensitivity"] == 0.6
    assert data["stt_model"] == "small"
    assert data["tts_voice"] == "en_US-amy-medium"


def test_voice_command_requires_share(client: TestClient):
    denied = client.post(
        "/voice/command",
        json={"transcript": "hello", "shared": False},
    )
    assert denied.status_code == 403


def test_voice_command_runs_master_bot(client: TestClient):
    response = client.post(
        "/voice/command",
        json={"transcript": "Remind me to buy milk", "shared": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "Remind me to buy milk"
    assert data["reply"]


def test_voice_ui_served(client: TestClient):
    response = client.get("/ui/voice.html")
    assert response.status_code == 200
    assert b"Voice Bot" in response.content
    assert b"Start listening" in response.content


def test_home_ui_served(client: TestClient):
    response = client.get("/ui/home.html")
    assert response.status_code == 200
    assert b"Voice Bot" in response.content
    assert b"/ui/voice.html" in response.content