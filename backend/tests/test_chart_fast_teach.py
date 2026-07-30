from __future__ import annotations

from app.web_learning.intent import is_chart_learn_ask


def test_is_chart_learn_ask():
    assert is_chart_learn_ask(
        "https://www.tradingview.com/chart/. learn how to read trade charts"
    )
    assert not is_chart_learn_ask("hello there")
    assert not is_chart_learn_ask("search for python docs")


def test_chart_learn_returns_local_lesson_without_internet(client):
    """Should not hang on DuckDuckGo / TradingView; teach from local skill pack."""
    resp = client.post(
        "/voice/command",
        json={
            "transcript": (
                "https://www.tradingview.com/chart/. "
                "Can youy go though webiste use the web bot and learn how to read trade charts"
            ),
            "shared": True,
            "speak": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    text = body["reply"].lower()
    assert "candlestick" in text or "open" in text
    assert "step 1: visit" not in text
    assert body.get("requires_permission") is False
