from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_SEARCH_ENGINES = {
    "google": "https://www.google.com/search",
    "duckduckgo": "https://html.duckduckgo.com/html/",
    "bing": "https://www.bing.com/search",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Reliable non-JS headline sources for current-affairs asks.
_NEWS_FEEDS = (
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Top Stories", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("Guardian World", "https://www.theguardian.com/world/rss"),
)


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


def _clean_google_url(href: str) -> str:
    """Unwrap /url?q=… redirect links from Google HTML results."""
    if href.startswith("/url?") or "google." in urlparse(href).netloc and "/url" in href:
        parsed = urlparse(href if href.startswith("http") else f"https://www.google.com{href}")
        params = parse_qs(parsed.query)
        for key in ("q", "url"):
            if key in params and params[key][0].startswith("http"):
                return unquote(params[key][0])
    return href


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(cleaned)).strip()


async def fetch_news_headlines(*, limit: int = 8) -> list[SearchResult]:
    """Fetch real article headlines from public RSS feeds (no JS portals)."""
    timeout = httpx.Timeout(8.0, connect=3.0)
    results: list[SearchResult] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for source_name, feed_url in _NEWS_FEEDS:
            if len(results) >= limit:
                break
            try:
                response = await client.get(feed_url, headers=_BROWSER_HEADERS)
                response.raise_for_status()
                root = ET.fromstring(response.text)
            except Exception:
                continue

            items = root.findall(".//item")
            if not items:
                ns = {"a": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//a:entry", ns)

            for item in items:
                title_el = item.find("title")
                if title_el is None:
                    title_el = item.find("{http://www.w3.org/2005/Atom}title")
                link_el = item.find("link")
                if link_el is None:
                    link_el = item.find("{http://www.w3.org/2005/Atom}link")
                desc_el = item.find("description")
                if desc_el is None:
                    desc_el = item.find("{http://www.w3.org/2005/Atom}summary")

                title = _strip_html(title_el.text if title_el is not None else "")
                if link_el is not None and link_el.get("href"):
                    url = (link_el.get("href") or "").strip()
                else:
                    url = _strip_html(link_el.text if link_el is not None else "")
                snippet = _strip_html(desc_el.text if desc_el is not None else "")
                if not title or not url.startswith("http"):
                    continue
                key = title.lower()
                if key in seen or len(title) < 20:
                    continue
                seen.add(key)
                if not snippet:
                    snippet = f"Headline from {source_name}."
                else:
                    snippet = f"{source_name}: {snippet[:220]}"
                results.append(SearchResult(title=title, url=url, snippet=snippet))
                if len(results) >= limit:
                    break

    return results


class WebSearchClient:
    def __init__(self, engine: str = "google") -> None:
        engine_l = (engine or "google").lower()
        self._engine = engine_l if engine_l in _SEARCH_ENGINES else "google"
        self._google_api_key = os.getenv("PROJECT_WE_GOOGLE_API_KEY", "").strip()
        self._google_cse_id = os.getenv("PROJECT_WE_GOOGLE_CSE_ID", "").strip()

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        if self._engine == "google":
            results = await self._search_google(query, limit=limit)
            if results:
                return results
            logger.warning("Google search empty for %r; falling back to Bing", query)
            bing = WebSearchClient(engine="bing")
            results = await bing._search_http(query, limit=limit)
            if results:
                self._engine = "bing"
                return results
            ddg = WebSearchClient(engine="duckduckgo")
            results = await ddg._search_http(query, limit=limit)
            if results:
                self._engine = "duckduckgo"
            return results

        return await self._search_http(query, limit=limit)

    async def _search_google(self, query: str, *, limit: int) -> list[SearchResult]:
        if self._google_api_key and self._google_cse_id:
            api_hits = await self._search_google_cse(query, limit=limit)
            if api_hits:
                return api_hits

        # Google News RSS is the most reliable key-free Google source.
        rss_hits = await self._search_google_news_rss(query, limit=limit)
        if rss_hits:
            return rss_hits

        html_hits = await self._search_google_html(query, limit=limit)
        useful = [
            h
            for h in html_hits
            if "support.google.com" not in h.url
            and "accounts.google.com" not in h.url
            and h.title.lower() not in {"feedback", "sign in", "images", "videos", "maps", "news"}
        ]
        return useful

    async def _search_google_cse(self, query: str, *, limit: int) -> list[SearchResult]:
        timeout = httpx.Timeout(10.0, connect=3.0)
        params = {
            "key": self._google_api_key,
            "cx": self._google_cse_id,
            "q": query,
            "num": min(max(limit, 1), 10),
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                headers=_BROWSER_HEADERS,
            )
            response.raise_for_status()
            body = response.json()

        results: list[SearchResult] = []
        for item in body.get("items") or []:
            title = (item.get("title") or "").strip()
            url = (item.get("link") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            if title and url.startswith("http"):
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break
        return results

    async def _search_google_html(self, query: str, *, limit: int) -> list[SearchResult]:
        timeout = httpx.Timeout(10.0, connect=3.0)
        # gbv=1 requests the simpler HTML results page.
        params = {"q": query, "hl": "en", "gl": "us", "gbv": "1", "num": str(min(limit, 10))}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                _SEARCH_ENGINES["google"],
                params=params,
                headers=_BROWSER_HEADERS,
            )
            response.raise_for_status()
            html = response.text

        if "unusual traffic" in html.lower() or "captcha" in html.lower():
            logger.warning("Google HTML blocked by captcha/traffic check")
            return []
        return self._parse_google(html, limit=limit)

    async def _search_google_news_rss(self, query: str, *, limit: int) -> list[SearchResult]:
        timeout = httpx.Timeout(8.0, connect=3.0)
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                "https://news.google.com/rss/search",
                params=params,
                headers=_BROWSER_HEADERS,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)

        results: list[SearchResult] = []
        for item in root.findall(".//item"):
            title = _strip_html(item.findtext("title") or "")
            url = _strip_html(item.findtext("link") or "")
            snippet = _strip_html(item.findtext("description") or "")
            if not title or not url.startswith("http"):
                continue
            if not snippet:
                snippet = "Google News result."
            results.append(SearchResult(title=title, url=url, snippet=snippet[:280]))
            if len(results) >= limit:
                break
        return results

    async def _search_http(self, query: str, *, limit: int) -> list[SearchResult]:
        timeout = httpx.Timeout(8.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if self._engine == "duckduckgo":
                response = await client.post(
                    _SEARCH_ENGINES["duckduckgo"],
                    data={"q": query},
                    headers=_BROWSER_HEADERS,
                )
            else:
                response = await client.get(
                    _SEARCH_ENGINES.get(self._engine, _SEARCH_ENGINES["bing"]),
                    params={"q": query},
                    headers=_BROWSER_HEADERS,
                )
            response.raise_for_status()
            html = response.text
        return self._parse_results(html, limit=limit)

    def _parse_results(self, html: str, *, limit: int) -> list[SearchResult]:
        if self._engine == "bing":
            return self._parse_bing(html, limit=limit)
        if self._engine == "google":
            return self._parse_google(html, limit=limit)
        return self._parse_duckduckgo(html, limit=limit)

    def _parse_google(self, html: str, *, limit: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen: set[str] = set()
        # Classic result blocks: <a href="/url?q=..."><h3>Title</h3>
        pattern = re.compile(
            r'<a[^>]+href="([^"]+)"[^>]*>\s*(?:<h3[^>]*>|)<(?:h3|div)[^>]*>(.*?)</(?:h3|div)>',
            re.IGNORECASE | re.DOTALL,
        )
        # Also catch gbv=1 simpler anchors with text.
        simple = re.compile(
            r'<a href="(/url\?q=[^"]+|https?://(?!www\.google\.)[^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        candidates = list(pattern.finditer(html)) + list(simple.finditer(html))
        for match in candidates:
            raw_url = unescape(match.group(1))
            url = _clean_google_url(raw_url)
            title = _strip_html(match.group(2))
            if not title or not url.startswith("http"):
                continue
            host = urlparse(url).netloc.lower()
            if "google." in host and "/search" in url:
                continue
            key = title.lower()
            if key in seen or len(title) < 8:
                continue
            seen.add(key)
            # Nearby snippet: take a short window after the match.
            window = html[match.end() : match.end() + 500]
            snippet_match = re.search(
                r'<div[^>]*class="[^"]*(?:VwiC3b|s3v9rd|st)[^"]*"[^>]*>(.*?)</div>',
                window,
                re.IGNORECASE | re.DOTALL,
            )
            snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
            results.append(SearchResult(title=title, url=url, snippet=snippet[:280]))
            if len(results) >= limit:
                break
        return results

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
