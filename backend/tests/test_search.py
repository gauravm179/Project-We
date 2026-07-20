from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.search.service import SearchResult


def test_search_blocked_in_strict_local_never_mode(client, monkeypatch):
    """Search should be blocked when internet_mode is 'never'."""
    monkeypatch.setenv("PROJECT_WE_INTERNET_MODE", "never")

    from app.core.config import get_settings
    get_settings.cache_clear()

    response = client.post("/search", json={"query": "test"})
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_search_requires_permission_in_ask_mode(client):
    """Search should require permission approval in 'ask' mode."""
    response = client.post("/search", json={"query": "gold price today"})
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()


def test_chat_asks_permission_for_internet_query(client):
    """Chat should detect internet queries and ask permission."""
    response = client.post("/chat", json={"message": "What is the latest news about Tesla?"})
    assert response.status_code == 200
    data = response.json()
    assert data["requires_permission"] is True
    assert data["required_capability"] == "internet"
    assert data["permission_request_id"] is not None


def test_chat_with_approved_permission_triggers_search(client):
    """Chat should search the web when permission is approved."""
    # Step 1: ask a question that needs internet
    resp1 = client.post("/chat", json={"message": "What is the current price of Bitcoin?"})
    data1 = resp1.json()
    assert data1["requires_permission"] is True
    perm_id = data1["permission_request_id"]

    # Step 2: approve the permission
    client.post(f"/permissions/{perm_id}/decision", json={"approve": True})

    # Step 3: re-ask with permission_id
    mock_results = [
        SearchResult(title="Bitcoin Price", url="https://example.com", snippet="BTC is $65,000")
    ]
    with patch("app.brain.service.SearchService.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        resp2 = client.post(
            "/chat",
            json={
                "message": "What is the current price of Bitcoin?",
                "permission_id": perm_id,
            },
        )

    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["search_results_used"] is True
    assert len(data2["response"]) > 0


def test_chat_without_internet_keywords_works_normally(client):
    """Normal questions should not trigger permission flow."""
    response = client.post("/chat", json={"message": "What is 2 plus 2?"})
    assert response.status_code == 200
    data = response.json()
    assert data["requires_permission"] is False
    assert data["search_results_used"] is False


def test_search_service_searxng_fallback_to_ddg():
    """When SearXNG is unavailable, should fallback to DuckDuckGo."""
    from app.search.service import SearchService

    service = SearchService()

    mock_ddg_results = [
        SearchResult(title="Test", url="https://test.com", snippet="Test snippet")
    ]

    with patch.object(service, "_searxng_search", new_callable=AsyncMock) as mock_searx:
        mock_searx.return_value = []
        with patch.object(service, "_duckduckgo_search", new_callable=AsyncMock) as mock_ddg:
            mock_ddg.return_value = mock_ddg_results

            import asyncio
            results = asyncio.run(service.search("test query"))

    assert len(results) == 1
    assert results[0].title == "Test"
    mock_searx.assert_called_once()
    mock_ddg.assert_called_once()
