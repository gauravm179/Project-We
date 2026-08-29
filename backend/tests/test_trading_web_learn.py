from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.brain.router import route_message
from app.trading.web_learn import (
    build_learn_queries,
    is_trading_web_learn_ask,
    url_worth_capturing,
)
from app.web_learning.intent import extract_urls, sanitize_url
from app.web_learning.service import CaptureResult, SearchPersistResult


def test_route_trading_web_learn():
    assert (
        route_message("learn from Zerodha Varsity and TradingView").target == "trading-bot"
    )
    assert route_message("google tradingview candlestick support").target == "trading-bot"


def test_is_trading_web_learn_ask():
    assert is_trading_web_learn_ask("learn from the internet for trading")
    assert is_trading_web_learn_ask("study Zerodha Varsity candlesticks")
    assert not is_trading_web_learn_ask("what time is it")


def test_build_learn_queries_prefers_sites():
    qs = build_learn_queries("learn from Zerodha and TradingView candlesticks", limit=4)
    assert any("zerodha" in q.lower() for q in qs)
    assert any("tradingview" in q.lower() for q in qs)


def test_url_worth_capturing_filters_chart_widgets():
    assert url_worth_capturing("https://zerodha.com/varsity/module/technical-analysis/")
    assert url_worth_capturing("https://www.tradingview.com/support/solutions/43000502338/")
    assert url_worth_capturing("https://in.tradingview.com/ideas/tradingviewchart/")
    assert not url_worth_capturing("https://www.tradingview.com/chart/AAPL/")


def test_sanitize_url_strips_smart_quotes():
    dirty = "https://in.tradingview.com/ideas/tradingviewchart/\u201d"
    assert sanitize_url(dirty) == "https://in.tradingview.com/ideas/tradingviewchart/"
    assert extract_urls(f'learn from "{dirty}"')[0].endswith("tradingviewchart/")


def test_build_learn_queries_tradingview_ideas():
    qs = build_learn_queries(
        "learn from https://in.tradingview.com/ideas/tradingviewchart/ chart ideas",
        limit=5,
    )
    assert any("ideas" in q.lower() for q in qs)


def test_direct_url_tradingview_ideas_learn(monkeypatch):
    import asyncio

    from app.trading import web_learn as wl

    ideas_url = "https://in.tradingview.com/ideas/tradingviewchart/"
    capture = CaptureResult(
        capture_id=11,
        url=ideas_url,
        title="TradingView chart ideas",
        summary=(
            "Chart ideas explain setups with annotated charts. Look for trend structure, "
            "support resistance, and risk reward on each idea before copying a trade."
        ),
        text_chars=300,
        image_count=0,
        compressed_bytes=50,
    )

    web = MagicMock()
    web.internet_allowed.return_value = True
    web.search_web = AsyncMock()
    web.capture_url = AsyncMock(return_value=capture)

    saved = []

    class FakeStore:
        def record(self, db, **kwargs):
            rec = MagicMock()
            rec.id = len(saved) + 1
            rec.title = kwargs["title"]
            saved.append(kwargs)
            return rec

    monkeypatch.setattr(wl, "LocalLearningStore", FakeStore)
    result = asyncio.run(
        wl.run_trading_web_learn(
            MagicMock(),
            web,
            user_message=f"learn from {ideas_url} and save important notes",
            max_queries=0,
            max_captures=2,
        )
    )
    assert result.captured >= 1
    assert len(result.saved) >= 1
    web.capture_url.assert_called()
    assert ideas_url in str(web.capture_url.call_args)


def test_run_trading_web_learn_saves_imp(monkeypatch):
    import asyncio

    from app.trading import web_learn as wl

    search = SearchPersistResult(
        search_id=1,
        engine="google",
        query="site:zerodha.com/varsity candlestick",
        result_count=1,
        compressed_bytes=10,
        results=[
            SearchResult(
                title="Candlestick charts — Varsity",
                url="https://zerodha.com/varsity/chapter/candlestick-charts/",
                snippet="How to read candlestick charts for technical analysis beginners.",
            )
        ],
    )
    capture = CaptureResult(
        capture_id=9,
        url="https://zerodha.com/varsity/chapter/candlestick-charts/",
        title="Candlestick charts — Varsity",
        summary=(
            "Candlesticks show open high low close. Long wicks mean rejection. "
            "Bodies show conviction. Use with trend and support resistance."
        ),
        text_chars=200,
        image_count=0,
        compressed_bytes=50,
    )

    web = MagicMock()
    web.internet_allowed.return_value = True
    web.search_web = AsyncMock(return_value=search)
    web.capture_url = AsyncMock(return_value=capture)

    saved = []

    class FakeStore:
        def record(self, db, **kwargs):
            rec = MagicMock()
            rec.id = len(saved) + 1
            rec.title = kwargs["title"]
            saved.append(kwargs)
            return rec

    monkeypatch.setattr(wl, "LocalLearningStore", FakeStore)
    result = asyncio.run(
        wl.run_trading_web_learn(
            MagicMock(),
            web,
            user_message="learn from Zerodha Varsity candlesticks",
            max_queries=1,
            max_captures=1,
        )
    )
    assert result.captured == 1
    assert len(result.saved) >= 1
    assert any(s.get("kind") == "trading-imp" for s in saved)


def test_trading_status_and_learnings(client: TestClient):
    status = client.get("/trading/status")
    assert status.status_code == 200
    data = status.json()
    assert data["bot"] == "trading-bot"
    assert data["enabled"] is True
    assert "learn_url" in data

    learnings = client.get("/trading/learnings")
    assert learnings.status_code == 200
    assert isinstance(learnings.json(), list)
