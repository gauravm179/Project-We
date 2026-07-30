from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

_SEARCH_ENGINES = {
    "duckduckgo": "https://html.duckduckgo.com/html/",
    "bing": "https://www.bing.com/search",
}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def _clean_ddg_url(href: str) -> str:
    if "uddg=" in href:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])
    return href


class WebSearchClient:
    def __init__(self, engine: str = "duckduckgo") -> None:
        self._engine = engine if engine in _SEARCH_ENGINES else "duckduckgo"

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        timeout = httpx.Timeout(8.0, connect=3.0)
        headers = {"User-Agent": "ProjectWe-WebLearner/0.3"}

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if self._engine == "duckduckgo":
                response = await client.post(
                    _SEARCH_ENGINES["duckduckgo"],
                    data={"q": query},
                    headers=headers,
                )
            else:
                response = await client.get(
                    _SEARCH_ENGINES["bing"],
                    params={"q": query},
                    headers=headers,
                )
            response.raise_for_status()
            html = response.text

        return self._parse_results(html, limit=limit)

    def _parse_results(self, html: str, *, limit: int) -> list[SearchResult]:
        if self._engine == "bing":
            return self._parse_bing(html, limit=limit)
        return self._parse_duckduckgo(html, limit=limit)

    def _parse_duckduckgo(self, html: str, *, limit: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        blocks = re.split(r'<div class="result\s', html)
        for block in blocks[1:]:
            title_match = re.search(
                r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.IGNORECASE | re.DOTALL,
            )
            snippet_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</a>',
                block,
                re.IGNORECASE | re.DOTALL,
            )
            if not title_match:
                continue
            url = _clean_ddg_url(unescape(title_match.group(1)))
            title = re.sub(r"<[^>]+>", "", title_match.group(2))
            title = unescape(title).strip()
            snippet = ""
            if snippet_match:
                snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1))
                snippet = unescape(snippet).strip()
            if title and url.startswith("http"):
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break
        return results

    def _parse_bing(self, html: str, *, limit: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        for match in re.finditer(
            r'<li class="b_algo".*?<a href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<p[^>]*>(.*?)</p>',
            html,
            re.IGNORECASE | re.DOTALL,
        ):
            url = unescape(match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2))
            title = unescape(title).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3))
            snippet = unescape(snippet).strip()
            if title and url.startswith("http"):
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break
        return results
