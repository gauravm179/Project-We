from __future__ import annotations


def test_voice_command_returns_reply_on_internal_error(client, monkeypatch):
    async def boom(transcript: str, *, speak: bool = False):
        raise RuntimeError("simulated web failure")

    monkeypatch.setattr(
        "app.api.routes.voice.voice_assistant.handle_command",
        boom,
    )
    resp = client.post(
        "/voice/command",
        json={
            "transcript": "https://www.tradingview.com/chart/ learn how to read trade charts",
            "shared": True,
            "speak": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body["reply"].lower() or "RuntimeError" in body["reply"]
    assert "voice error" in (body.get("route_reason") or "")
