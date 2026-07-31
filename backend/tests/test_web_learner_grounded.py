from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.web_learning.search import SearchResult
from app.web_learning.service import WebAssistResult, WebLearningService


def _approve_internet(client: TestClient) -> None:
    pending = client.get("/permissions?status=pending").json()
    if pending:
        client.post(f"/permissions/{pending[-1]['id']}/decision", json={"approve": True})
        return
    created = client.post(
        "/permissions",
        json={"capability": "internet", "reason": "test"},
    ).json()
    client.post(f"/permissions/{created['id']}/decision", json={"approve": True})


def test_compose_grounded_skill_reply_teaches_from_evidence():
    assist = WebAssistResult(
        context=(
            "WEB LEARNER ASSIST for web-learner-bot:\n"
            "Search #1 (duckduckgo): how to read candlestick charts\n"
            "1. Candlestick basics\n"
            "   URL: https://example.com/candles\n"
            "   Learn open high low close and wick meaning\n"
            "Skipped capture of interactive chart page (https://www.tradingview.com/chart/).\n"
            "Captured #9: Candle guide (https://example.com/candles)\n"
            "Summary: Candlestick charts show open high low close for each period."
        ),
        search_id=1,
        capture_ids=(9,),
    )
    text = WebLearningService().compose_grounded_skill_reply(
        "https://www.tradingview.com/chart/ learn how to read trade charts",
        assist,
    )
    assert "web-learner skills" in text.lower()
    assert "step 1: visit" not in text.lower()
    assert "navigate to the following url" not in text.lower()
    assert "Candlestick" in text or "candlestick" in text.lower()
    assert "#9" in text or "Captured #9" in text
    assert "tradingview canvas" in text.lower()


def test_compose_news_briefing_not_link_dump():
    assist = WebAssistResult(
        context=(
            "WEB LEARNER ASSIST for web-learner-bot:\n"
            "Search #4 (duckduckgo): top world news stories today\n"
            "1. Google News - World - Latest\n"
            "   URL: https://news.google.com/topics/abc\n"
            "   Read full articles, watch videos, browse thousands of titles and more\n"
            "2. World | Latest News & Updates | BBC News\n"
            "   URL: https://www.bbc.com/news/world\n"
            "   Get all the latest news, live updates and content about the World from across the BBC.\n"
            "3. India and Japan sign new trade pact\n"
            "   URL: https://www.bbc.com/news/world-asia-123\n"
            "   Leaders agreed a multi-year partnership covering semiconductors and clean energy.\n"
            "Captured #12: BBC World (https://www.bbc.com/news/world)\n"
            "Summary: Headlines: Storms disrupt flights across Europe | Cabinet clears new education policy | UN warns on climate targets"
        ),
        search_id=4,
        capture_ids=(12,),
    )
    text = WebLearningService().compose_grounded_skill_reply(
        "current affair for today",
        assist,
    )
    lower = text.lower()
    assert "fetched" in lower or "headlines" in lower or "briefing" in lower
    assert "india and japan" in lower or "storms disrupt" in lower
    assert "tradingview" not in lower
    assert "what search found" not in lower
    assert "read full articles, watch videos" not in lower
    assert "https://news.google.com" not in text
    assert "get all the latest news, live updates" not in lower
    assert "why it" in lower or "themes" in lower or "questions" in lower


def test_news_thinking_helpers_cluster_and_question():
    from app.web_learning.news_curriculum import (
        classify_themes,
        follow_up_questions,
        why_it_matters,
    )

    themes = classify_themes(
        [
            "If Hamas disarmament plan holds, Gaza war may shift",
            "About 60,000 migrants arrive in Ceuta in 24 hours",
            "Fifa says nobody selling football as plan continues",
        ]
    )
    names = {t for t, _ in themes}
    assert "Geopolitics / conflict" in names
    assert "Migration / borders" in names
    assert why_it_matters(themes)
    qs = follow_up_questions(themes)
    assert len(qs) >= 2
    assert any("?" in q for q in qs)


def test_web_learner_chat_uses_skills_not_browser_fluff(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    html = (
        "<html><head><title>Candle Guide</title></head>"
        "<body><p>"
        + ("Candlestick open high low close support resistance volume. " * 20)
        + "</p></body></html>"
    )

    class FakeResponse:
        def __init__(self, text: str = "", content: bytes = b"", content_type: str = "text/html"):
            self.text = text
            self.content = content
            self.headers = {"content-type": content_type}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            return FakeResponse(text=html)

    async def fake_search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="How to read candlestick charts",
                url="https://example.com/candles",
                snippet="Candlestick open high low close explained for beginners",
            )
        ]

    monkeypatch.setattr("app.web_learning.service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.web_learning.search.WebSearchClient.search", fake_search)
    _approve_internet(client)

    resp = client.post(
        "/chat",
        json={
            "message": (
                "https://www.tradingview.com/chart/. "
                "Can you go through website use the web bot and learn how to read trade charts"
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()["response"].lower()
    assert "step 1: visit" not in body
    assert "navigate to the following url" not in body
    assert "candlestick" in body or "web-learner skills" in body or "search" in body
    assert "web-learner skills" in body or "captured #" in body or "what search found" in body
    assert body.startswith("[via web learner]") or "web" in body
