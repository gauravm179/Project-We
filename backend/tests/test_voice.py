from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_voice_status_available(client):
    response = client.get("/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert "wake_word" in data


def test_voice_start_and_stop_routes(client):
    with patch("app.api.routes.voice.voice_assistant.start", new_callable=AsyncMock) as mock_start:
        response = client.post("/voice/start")
        assert response.status_code == 200
        mock_start.assert_called_once()

    with patch("app.api.routes.voice.voice_assistant.stop", new_callable=AsyncMock) as mock_stop:
        response = client.post("/voice/stop")
        assert response.status_code == 200
        mock_stop.assert_called_once()


def test_voice_config_patch(client):
    response = client.patch(
        "/voice/config",
        json={
            "wake_word": "ducus",
            "wake_sensitivity": 0.6,
            "stt_model": "small",
            "tts_voice": "en_US-amy-medium",
            "silence_threshold": 2.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["wake_word"] == "ducus"
    assert data["wake_sensitivity"] == 0.6
    assert data["stt_model"] == "small"
    assert data["tts_voice"] == "en_US-amy-medium"

