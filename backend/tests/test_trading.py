from __future__ import annotations

from fastapi.testclient import TestClient

from app.brain.router import route_message
from app.brain.model_router import choose_model_tier
from app.trading.intent import (
    company_news_query,
    extract_tickers,
    format_webhook_as_user_message,
    is_trading_ask,
    wants_company_news,
)
from app.trading.service import compose_trading_analysis


def test_route_trading_asks():
    assert route_message("analyze AAPL chart support resistance").target == "trading-bot"
    assert route_message("ask trading bot about TSLA outlook").target == "trading-bot"
    assert route_message("TradingView alert fired on NVDA").target == "trading-bot"


def test_chart_curriculum_still_web_learner():
    decision = route_message("I want a bot that can read all chart types and store skills locally")
    assert decision.target == "web-learner-bot"


def test_trading_bot_uses_tech_model():
    choice = choose_model_tier("hello", specialist_slug="trading-bot")
    assert choice.tier == "tech"


def test_extract_tickers_and_news_query():
    assert extract_tickers("Look at $AAPL and MSFT") == ["AAPL", "MSFT"]
    assert wants_company_news("AAPL earnings news today")
    q = company_news_query("Analyze AAPL candle breakout")
    assert q is not None
    assert "AAPL" in q


def test_is_trading_ask():
    assert is_trading_ask("give me a trading bias with stop loss")
    assert is_trading_ask("NVDA")
    assert not is_trading_ask("what time is it")


def test_format_webhook_prompt():
    text = format_webhook_as_user_message(
        {"ticker": "AAPL", "action": "buy", "price": 190, "interval": "1h", "message": "breakout"}
    )
    assert "AAPL" in text
    assert "buy" in text.lower()
    assert "Do not guarantee profits" in text


def test_compose_trading_analysis_grounded():
    reply = compose_trading_analysis("Analyze AAPL support resistance on the candle chart")
    assert "AAPL" in reply
    assert "invalidation" in reply.lower() or "Invalidation" in reply
    assert "not financial advice" in reply.lower() or "not a guarantee" in reply.lower()


def test_trading_status_endpoint(client: TestClient):
    resp = client.get("/trading/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bot"] == "trading-bot"
    assert "/trading/webhooks/tradingview" in data["webhook_url"]


def test_tradingview_webhook_store_without_analyze(client: TestClient):
    resp = client.post(
        "/trading/webhooks/tradingview?analyze=false",
        json={
            "ticker": "AAPL",
            "action": "buy",
            "price": 190.5,
            "interval": "1h",
            "message": "breakout",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["action"] == "buy"
    assert data["analysis"] is None
    assert "stored" in data["message"].lower()

    recent = client.get("/trading/webhooks/recent").json()
    assert any(r["id"] == data["id"] for r in recent)


def test_trading_bot_bootstrap_present(client: TestClient):
    resp = client.get("/specialists/trading-bot")
    assert resp.status_code == 200
    bot = resp.json()
    assert bot["slug"] == "trading-bot"
    assert bot["enabled"] is True


def test_chat_routes_to_trading_bot(client: TestClient):
    resp = client.post("/chat", json={"message": "analyze AAPL chart bias and support"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["routed_to"] == "trading-bot"
