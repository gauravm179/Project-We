from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchService:
    """Web search with SearXNG (primary) and DuckDuckGo (fallback)."""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        results = await self._searxng_search(query, max_results)
        if results:
            return results

        logger.info("SearXNG unavailable, falling back to DuckDuckGo")
        return await self._duckduckgo_search(query, max_results)

    async def _searxng_search(self, query: str, max_results: int) -> list[SearchResult]:
        settings = get_settings()
        base_url = settings.searxng_base_url
        if not base_url:
            return []

        try:
            url = f"{base_url}/search"
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "en",
            }
            timeout = httpx.Timeout(15.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                ))
            return results
        except Exception as e:
            logger.warning("SearXNG search failed: %s", e)
            return []

    async def _duckduckgo_search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for item in raw_results:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=item.get("body", ""),
                ))
            return results
        except ImportError:
            logger.warning("duckduckgo-search not installed, fallback unavailable")
            return []
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)
            return []
