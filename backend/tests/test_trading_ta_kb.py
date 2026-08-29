from __future__ import annotations

from fastapi.testclient import TestClient

from app.brain.router import route_message
from app.trading.ta_curriculum import TA_TOPICS
from app.trading.ta_kb import is_ta_kb_install_ask


def test_ta_topics_cover_all_categories():
    cats = {t["category"] for t in TA_TOPICS}
    assert "chart-type" in cats
    assert "pattern" in cats
    assert "indicator" in cats
    assert "scenario" in cats
    assert len(TA_TOPICS) >= 30


def test_is_ta_kb_install_ask():
    assert is_ta_kb_install_ask("install all technical analysis chart types locally")
    assert is_ta_kb_install_ask("learn all chart types from tradingview")
    assert not is_ta_kb_install_ask("what is the weather")


def test_route_ta_kb_to_trading_bot():
    assert route_message("install full ta knowledge base").target == "trading-bot"


def test_install_ta_kb_local_api(client: TestClient):
    resp = client.post("/trading/install-ta-kb/local")
    assert resp.status_code == 200
    data = resp.json()
    assert data["topic_count"] >= 30
    assert data["topic_count"] == len(TA_TOPICS)
    assert "Technical Analysis KB installed" in data["reply"]


def test_trading_status_includes_ta_kb(client: TestClient):
    resp = client.get("/trading/status")
    assert resp.status_code == 200
    assert resp.json()["ta_kb_topics"] == len(TA_TOPICS)
