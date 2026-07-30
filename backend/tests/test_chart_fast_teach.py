from __future__ import annotations

from pathlib import Path

from app.web_learning.chart_curriculum import CURRICULUM_DIR, CHART_LESSONS
from app.web_learning.intent import is_chart_curriculum_ask, is_chart_learn_ask


def test_is_chart_learn_ask():
    assert is_chart_learn_ask(
        "https://www.tradingview.com/chart/. learn how to read trade charts"
    )
    assert not is_chart_learn_ask("hello there")
    assert not is_chart_learn_ask("search for python docs")


def test_curriculum_ask_not_fast_teach():
    msg = (
        "i want a bot to learn reading all types of chart "
        "and should store all skills lolcally on laptop"
    )
    assert is_chart_curriculum_ask(msg)
    assert not is_chart_learn_ask(msg)


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
    assert "candlestick" in text or "candle" in text
    assert "heikin" in text or "line chart" in text or "line charts" in text
    assert "step 1: visit" not in text
    assert body.get("requires_permission") is False
    assert body.get("route_reason") == "fast local chart lesson"
    assert body.get("routed_to") == "web-learner-bot"


def test_curriculum_install_stores_skills_locally(client, tmp_path, monkeypatch):
    """Meta ask installs multi-chart skills to disk + SQLite for web-learner."""
    monkeypatch.setattr(
        "app.web_learning.chart_curriculum.CURRICULUM_DIR",
        tmp_path / "chart_curriculum",
    )
    # Also patch module-level import used after install for path in reply
    import app.web_learning.chart_curriculum as cc

    monkeypatch.setattr(cc, "CURRICULUM_DIR", tmp_path / "chart_curriculum")

    resp = client.post(
        "/voice/command",
        json={
            "transcript": (
                "i want a bot to learn reading all types of chart "
                "and should store all skills lolcally on laptop"
            ),
            "shared": True,
            "speak": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("routed_to") == "web-learner-bot"
    assert body.get("route_reason") == "local chart curriculum install"
    text = body["reply"].lower()
    assert "curriculum" in text or "skills" in text
    assert "candlestick" in text or "heikin" in text
    assert (tmp_path / "chart_curriculum" / "manifest.json").is_file()
    assert (tmp_path / "chart_curriculum" / "read-candlestick-charts.json").is_file()
    assert len(CHART_LESSONS) >= 6
