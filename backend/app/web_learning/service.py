from __future__ import annotations

import gzip
import io
import json
import logging
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR, get_settings
from app.db.models import Specialist, WebCapture, WebCaptureImage, WebSearch
from app.policy.service import PolicyService
from app.web_learning.intent import (
    extract_search_query,
    extract_urls,
    is_learn_intent,
    is_news_ask,
    is_valid_http_url,
    message_needs_web_assist,
)
from app.web_learning.search import SearchResult, WebSearchClient, fetch_news_headlines

logger = logging.getLogger(__name__)

WEB_LEARNING_DIR = DATA_DIR / "web_learning" / "captures"
SEARCH_DIR = DATA_DIR / "web_learning" / "searches"
WEB_LEARNER_SLUG = "web-learner-bot"
_IMG_SRC_PATTERN = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
_JS_HEAVY_HOST_PATTERN = re.compile(
    r"(?:^|\.)(?:tradingview\.com|binance\.com|coinbase\.com)$",
    re.IGNORECASE,
)


def _is_js_heavy_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    path = (urlparse(url).path or "").lower()
    if _JS_HEAVY_HOST_PATTERN.search(host):
        return True
    if "chart" in path and any(x in host for x in ("trading", "finance", "stock")):
        return True
    return False


_WEAK_NEWS_HOSTS = (
    "news.google.com",
    "google.com",
    "bing.com",
    "duckduckgo.com",
)
_WEAK_NEWS_SNIPPET_MARKERS = (
    "read full articles",
    "watch videos, browse thousands",
    "latest news and breaking news today",
    "get all the latest news, live updates",
    "follow the latest international",
    "stay informed with top world news",
    "from your trusted online news source",
    "aims to keep you up-to-date",
    "breaking stories and global current events",
)
_WEAK_NEWS_TITLE_MARKERS = (
    "latest top stories",
    "latest news & updates",
    "top & breaking world news",
    "google news",
)


def _is_weak_news_hit(title: str, url: str, snippet: str) -> bool:
    """True for aggregator/portal hits that don't carry a usable headline."""
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    if any(host == h or host.endswith("." + h) for h in _WEAK_NEWS_HOSTS):
        return True
    path = (urlparse(url).path or "").rstrip("/")
    snippet_l = (snippet or "").lower()
    title_l = (title or "").lower()
    if any(m in snippet_l for m in _WEAK_NEWS_SNIPPET_MARKERS):
        return True
    if any(m in title_l for m in _WEAK_NEWS_TITLE_MARKERS):
        return True
    if title_l.startswith("google news") or title_l in {"cnn", "bbc news", "world"}:
        return True
    # Bare section pages (…/world, …/news) usually aren't article headlines.
    if path in {"", "/", "/news", "/news/world", "/world", "/world-news"}:
        return True
    if len((snippet or "").strip()) < 40:
        return True
    return False


def _extract_news_headlines(html: str, *, limit: int = 8) -> list[str]:
    """Pull likely article headlines from a news HTML page."""
    headlines: list[str] = []
    seen: set[str] = set()
    patterns = (
        r"<h[123][^>]*>\s*(?:<a[^>]*>)?\s*([^<]{20,160})\s*(?:</a>)?\s*</h[123]>",
        r'<a[^>]+href="[^"]*(?:/news/|/world/|/article|/story|/current-affairs)[^"]*"[^>]*>\s*([^<]{25,160})\s*</a>',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            title = re.sub(r"\s+", " ", unescape(match.group(1))).strip(" -|•")
            key = title.lower()
            if (
                len(title) < 25
                or key in seen
                or any(m in key for m in _WEAK_NEWS_TITLE_MARKERS)
                or key.startswith(("skip to", "sign in", "subscribe", "menu", "search"))
            ):
                continue
            seen.add(key)
            headlines.append(title)
            if len(headlines) >= limit:
                return headlines
    return headlines


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


@dataclass(frozen=True)
class CaptureResult:
    capture_id: int
    url: str
    title: str
    text_chars: int
    image_count: int
    compressed_bytes: int
    summary: str


@dataclass(frozen=True)
class SearchPersistResult:
    search_id: int
    engine: str
    query: str
    result_count: int
    compressed_bytes: int
    results: list[SearchResult]


@dataclass(frozen=True)
class WebAssistResult:
    context: str
    search_id: int | None = None
    capture_ids: tuple[int, ...] = ()
    requires_permission: bool = False
    permission_request_id: int | None = None
    message: str | None = None


class WebLearningService:
    def __init__(self) -> None:
        self._policy = PolicyService()
        WEB_LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        SEARCH_DIR.mkdir(parents=True, exist_ok=True)

    def _permission_block(
        self, db: Session, reason: str
    ) -> dict[str, object]:
        request = self._policy.create_permission_request(
            db=db,
            capability="internet",
            reason=reason,
        )
        db.commit()
        return {
            "requires_permission": True,
            "required_capability": "internet",
            "permission_request_id": request.id,
            "message": (
                "Approve internet access so web-learner-bot can search or read pages. "
                "Reply yes / approved (or use the Approve button)."
            ),
        }

    async def search_web(
        self,
        db: Session,
        query: str,
        *,
        engine: str | None = None,
        limit: int = 5,
        auto_capture_top: bool = False,
    ) -> SearchPersistResult | dict[str, object]:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == WEB_LEARNER_SLUG))
        if specialist is None:
            return {"error": "Web learner bot not found"}

        if not self.internet_allowed(db):
            return self._permission_block(db, f"Web search for: {query}")

        settings = get_settings()
        client = WebSearchClient(engine=engine or settings.web_search_engine)
        results = await client.search(query, limit=limit)

        row = WebSearch(
            specialist_id=specialist.id,
            engine=client._engine,
            query=query,
            result_count=len(results),
            compressed_bytes=0,
            storage_path="",
        )
        db.add(row)
        db.flush()

        search_dir = SEARCH_DIR / str(row.id)
        search_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "query": query,
            "engine": client._engine,
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet} for r in results
            ],
        }
        gz_path = search_dir / "results.json.gz"
        compressed = self._write_gzip_json(gz_path, payload)
        row.compressed_bytes = compressed
        row.storage_path = str(search_dir.relative_to(DATA_DIR))
        db.commit()
        db.refresh(row)

        if auto_capture_top and results:
            await self.capture_url(
                db,
                WEB_LEARNER_SLUG,
                results[0].url,
                max_images=3,
                allow_without_permission=True,
            )

        return SearchPersistResult(
            search_id=row.id,
            engine=client._engine,
            query=query,
            result_count=len(results),
            compressed_bytes=compressed,
            results=results,
        )

    async def assist_for_message(
        self,
        db: Session,
        message: str,
        *,
        requesting_bot: str,
        auto_capture_urls: bool = True,
        auto_search: bool = True,
        max_url_captures: int = 2,
    ) -> WebAssistResult | dict[str, object]:
        if not message_needs_web_assist(message):
            return WebAssistResult(context="")

        if not self.internet_allowed(db):
            blocked = self._permission_block(
                db,
                f"{requesting_bot} needs web-learner-bot for: {message[:200]}",
            )
            from app.progress import progress

            progress.step("web-permission", "Internet approval required")
            return WebAssistResult(
                context="",
                requires_permission=True,
                permission_request_id=int(blocked["permission_request_id"]),  # type: ignore[arg-type]
                message=str(blocked["message"]),
            )

        from app.progress import progress

        parts: list[str] = [
            f"WEB LEARNER ASSIST for {requesting_bot} (via web-learner-bot):"
        ]
        capture_ids: list[int] = []
        search_id: int | None = None

        if auto_search:
            query = extract_search_query(message)
            if query:
                progress.step("web-search", f"Searching: {query[:120]}")
                try:
                    search = await self.search_web(db, query, limit=5)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Web search failed for %r: %s", query, exc)
                    progress.step("web-search-error", f"{type(exc).__name__}: {exc}")
                    parts.append(f"Search failed ({query}): {exc}")
                    search = None
                if isinstance(search, dict):
                    return search
                if isinstance(search, SearchPersistResult):
                    search_id = search.search_id
                    progress.step(
                        "web-search-done",
                        f"#{search.search_id} hits={search.result_count} engine={search.engine}",
                    )
                    # Current affairs: prefer live RSS article headlines over portal SERP pages.
                    news_hits: list[SearchResult] = []
                    if is_news_ask(message):
                        progress.step("web-rss", "Fetching live news RSS headlines")
                        try:
                            news_hits = await fetch_news_headlines(limit=8)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("RSS headline fetch failed: %s", exc)
                            progress.step("web-rss-error", f"{type(exc).__name__}: {exc}")
                        if news_hits:
                            progress.step("web-rss-done", f"rss_hits={len(news_hits)}")

                    display_results = news_hits or list(search.results)
                    source_label = "rss+search" if news_hits else search.engine
                    parts.append(
                        f"Search #{search.search_id} ({source_label}): {search.query}"
                    )
                    for idx, result in enumerate(display_results, start=1):
                        parts.append(
                            f"{idx}. {result.title}\n   URL: {result.url}\n   {result.snippet}"
                        )
                    # Learning + news: capture readable pages so replies aren't just link dumps.
                    # When RSS already gave real headlines, skip slow page captures.
                    should_capture = (
                        auto_capture_urls
                        and (
                            is_learn_intent(message)
                            or (is_news_ask(message) and not news_hits)
                        )
                    )
                    capture_budget = 1
                    capture_candidates = news_hits[:3] if news_hits else search.results[:6]
                    if should_capture:
                        captured_n = 0
                        for result in capture_candidates:
                            if captured_n >= capture_budget:
                                break
                            if not is_valid_http_url(result.url) or _is_js_heavy_url(result.url):
                                continue
                            if (
                                not is_news_ask(message)
                                and _is_weak_news_hit(result.title, result.url, result.snippet)
                            ):
                                continue
                            progress.step("web-capture", f"Reading {result.url[:120]}")
                            try:
                                captured = await self.capture_url(
                                    db,
                                    WEB_LEARNER_SLUG,
                                    result.url,
                                    max_images=1,
                                    allow_without_permission=True,
                                )
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("Learn-capture failed for %s: %s", result.url, exc)
                                progress.step("web-capture-error", f"{type(exc).__name__}: {exc}")
                                continue
                            if isinstance(captured, CaptureResult):
                                capture_ids.append(captured.capture_id)
                                captured_n += 1
                                progress.step(
                                    "web-capture-done",
                                    f"#{captured.capture_id} chars={captured.text_chars}",
                                )
                                parts.append(
                                    f"Captured #{captured.capture_id}: {captured.title} ({captured.url})\n"
                                    f"Summary: {captured.summary}"
                                )
                                if not is_news_ask(message):
                                    break

        if auto_capture_urls:
            for url in extract_urls(message)[:max_url_captures]:
                if not is_valid_http_url(url):
                    continue
                if _is_js_heavy_url(url):
                    parts.append(
                        f"Skipped capture of interactive chart page ({url}). "
                        "Live chart apps are JavaScript-only; used search + tutorial pages instead."
                    )
                    progress.step("web-skip", f"JS-heavy page skipped: {url[:100]}")
                    continue
                progress.step("web-capture", f"Reading {url[:120]}")
                try:
                    captured = await self.capture_url(
                        db,
                        WEB_LEARNER_SLUG,
                        url,
                        max_images=2,
                        allow_without_permission=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Capture failed for %s: %s", url, exc)
                    progress.step("web-capture-error", f"{type(exc).__name__}: {exc}")
                    parts.append(f"Capture failed for {url}: {exc}")
                    continue
                if isinstance(captured, CaptureResult):
                    capture_ids.append(captured.capture_id)
                    progress.step(
                        "web-capture-done",
                        f"#{captured.capture_id} chars={captured.text_chars}",
                    )
                    note = ""
                    if captured.text_chars < 400:
                        note = (
                            "\nNote: little readable text on this page "
                            "(may be mostly interactive/JavaScript)."
                        )
                    parts.append(
                        f"Captured #{captured.capture_id}: {captured.title} ({captured.url})\n"
                        f"Summary: {captured.summary}{note}"
                    )

        return WebAssistResult(
            context="\n".join(parts),
            search_id=search_id,
            capture_ids=tuple(capture_ids),
        )

    def format_assist_context(self, assist: WebAssistResult) -> str:
        if not assist.context:
            return ""
        return assist.context

    def internet_allowed(self, db: Session) -> bool:
        return self._policy.has_approved_capability(db, "internet")

    async def capture_url(
        self,
        db: Session,
        specialist_slug: str,
        url: str,
        *,
        max_images: int = 8,
        allow_without_permission: bool = False,
    ) -> CaptureResult | dict[str, object]:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == specialist_slug))
        if specialist is None:
            return {"error": "Specialist not found"}

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return {"error": "Only http/https URLs are supported"}

        if not allow_without_permission and not self.internet_allowed(db):
            request = self._policy.create_permission_request(
                db=db,
                capability="internet",
                reason=f"Web learner needs internet to read: {url}",
            )
            db.commit()
            return {
                "requires_permission": True,
                "required_capability": "internet",
                "permission_request_id": request.id,
                "message": "Approve internet access, then capture again.",
            }

        timeout = httpx.Timeout(8.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "ProjectWe-WebLearner/0.3"})
            response.raise_for_status()
            html = response.text
            content_type = response.headers.get("content-type", "")

        if "html" not in content_type and not html.lstrip().startswith("<"):
            return {"error": "URL did not return HTML content"}

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", unescape(title_match.group(1))).strip() if title_match else url

        parser = _TextExtractor()
        parser.feed(html)
        page_text = parser.text()
        headlines = _extract_news_headlines(html, limit=8)
        if headlines:
            summary = "Headlines: " + " | ".join(headlines[:6])
        else:
            summary = page_text[:500]

        image_urls = self._extract_image_urls(html, base_url=url)[:max_images]

        row = WebCapture(
            specialist_id=specialist.id,
            url=url,
            title=title[:500],
            summary=summary[:800],
            text_chars=len(page_text),
            image_count=0,
            compressed_bytes=0,
            storage_path="",
        )
        db.add(row)
        db.flush()

        capture_dir = WEB_LEARNING_DIR / str(row.id)
        capture_dir.mkdir(parents=True, exist_ok=True)
        images_dir = capture_dir / "images"
        images_dir.mkdir(exist_ok=True)

        compressed_total = 0
        manifest_images: list[dict[str, object]] = []

        page_payload = {
            "url": url,
            "title": title,
            "text": page_text,
            "image_urls_found": len(image_urls),
        }
        page_gz = capture_dir / "page.json.gz"
        compressed_total += self._write_gzip_json(page_gz, page_payload)

        downloaded = 0
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for idx, image_url in enumerate(image_urls, start=1):
                try:
                    img_resp = await client.get(
                        image_url,
                        headers={"User-Agent": "ProjectWe-WebLearner/0.3"},
                    )
                    img_resp.raise_for_status()
                    raw = img_resp.content
                    compressed, filename = self._compress_image(raw, idx)
                    out_path = images_dir / filename
                    out_path.write_bytes(compressed)
                    compressed_total += len(compressed)

                    img_row = WebCaptureImage(
                        capture_id=row.id,
                        source_url=image_url[:2000],
                        filename=filename,
                        original_bytes=len(raw),
                        compressed_bytes=len(compressed),
                    )
                    db.add(img_row)
                    manifest_images.append(
                        {
                            "filename": filename,
                            "source_url": image_url,
                            "original_bytes": len(raw),
                            "compressed_bytes": len(compressed),
                        }
                    )
                    downloaded += 1
                except Exception as exc:  # noqa: BLE001 - keep capture resilient
                    logger.warning("Skipped image %s: %s", image_url, exc)

        manifest = {
            "capture_id": row.id,
            "url": url,
            "title": title,
            "text_chars": len(page_text),
            "images": manifest_images,
        }
        manifest_gz = capture_dir / "manifest.json.gz"
        compressed_total += self._write_gzip_json(manifest_gz, manifest)

        row.image_count = downloaded
        row.compressed_bytes = compressed_total
        row.storage_path = str(capture_dir.relative_to(DATA_DIR))
        db.commit()
        db.refresh(row)

        return CaptureResult(
            capture_id=row.id,
            url=url,
            title=title,
            text_chars=len(page_text),
            image_count=downloaded,
            compressed_bytes=compressed_total,
            summary=summary[:280] + ("..." if len(summary) > 280 else ""),
        )

    def list_captures(self, db: Session, specialist_slug: str, limit: int = 50) -> list[dict]:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == specialist_slug))
        if specialist is None:
            return []

        rows = db.scalars(
            select(WebCapture)
            .where(WebCapture.specialist_id == specialist.id)
            .order_by(WebCapture.id.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": row.id,
                "url": row.url,
                "title": row.title,
                "summary": row.summary,
                "text_chars": row.text_chars,
                "image_count": row.image_count,
                "compressed_bytes": row.compressed_bytes,
                "storage_path": row.storage_path,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

    def get_capture(self, db: Session, specialist_slug: str, capture_id: int) -> dict | None:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == specialist_slug))
        if specialist is None:
            return None

        row = db.scalar(
            select(WebCapture).where(
                WebCapture.id == capture_id,
                WebCapture.specialist_id == specialist.id,
            )
        )
        if row is None:
            return None

        capture_dir = DATA_DIR / row.storage_path
        page_text = ""
        page_file = capture_dir / "page.json.gz"
        if page_file.exists():
            page_text = self._read_gzip_json(page_file).get("text", "")

        images = db.scalars(
            select(WebCaptureImage).where(WebCaptureImage.capture_id == row.id)
        ).all()

        return {
            "id": row.id,
            "url": row.url,
            "title": row.title,
            "text": page_text,
            "text_chars": row.text_chars,
            "image_count": row.image_count,
            "compressed_bytes": row.compressed_bytes,
            "storage_path": row.storage_path,
            "images": [
                {
                    "filename": img.filename,
                    "source_url": img.source_url,
                    "original_bytes": img.original_bytes,
                    "compressed_bytes": img.compressed_bytes,
                }
                for img in images
            ],
            "created_at": row.created_at.isoformat(),
        }

    def compose_grounded_skill_reply(
        self,
        user_message: str,
        assist: WebAssistResult,
    ) -> str:
        """Build a teaching reply from real search/capture skill output (no invented browsing)."""
        context = (assist.context or "").strip()
        if not context:
            return (
                "I could not fetch web evidence yet. Approve internet access, then ask again "
                "with a URL or ‘search for …’ / ‘learn how to …’."
            )

        search_hits: list[dict[str, str]] = []
        capture_lines: list[str] = []
        notes: list[str] = []
        current: dict[str, str] | None = None
        for raw in context.splitlines():
            line = raw.strip()
            if not line or line.startswith("WEB LEARNER ASSIST"):
                continue
            if line.startswith("Search #"):
                notes.append(line)
                continue
            if line.startswith("Skipped capture") or line.startswith("Search failed") or line.startswith("Capture failed"):
                notes.append(line)
                continue
            if line.startswith("Captured #"):
                if current:
                    search_hits.append(current)
                    current = None
                capture_lines.append(line)
                continue
            if line.startswith("Summary:"):
                if capture_lines:
                    capture_lines[-1] = f"{capture_lines[-1]}\n  {line}"
                continue
            numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
            if numbered:
                if current:
                    search_hits.append(current)
                current = {"title": numbered.group(2).strip(), "url": "", "snippet": ""}
                continue
            if line.startswith("URL:") and current is not None:
                current["url"] = line.removeprefix("URL:").strip()
                continue
            if current is not None and not line.startswith("Captured"):
                # snippet under a search hit
                if current["snippet"]:
                    current["snippet"] += " " + line
                else:
                    current["snippet"] = line
        if current:
            search_hits.append(current)

        if is_news_ask(user_message):
            return self._compose_news_briefing(
                search_hits=search_hits,
                capture_lines=capture_lines,
                notes=notes,
                capture_ids=assist.capture_ids,
            )

        search_lines = [
            (
                f"{i}. {hit['title']}"
                + (f"\n   URL: {hit['url']}" if hit["url"] else "")
                + (f"\n   {hit['snippet']}" if hit["snippet"] else "")
            )
            for i, hit in enumerate(search_hits, start=1)
        ]

        parts: list[str] = [
            "I used web-learner skills (web-search + read-web-page / compress-store-learning) "
            "on real fetched data — not made-up browser steps.",
        ]

        if notes:
            parts.append("Skill notes:")
            parts.extend(f"- {n}" for n in notes[:6])

        if search_lines:
            parts.append("\nWhat search found:")
            parts.extend(search_lines[:5])

        if capture_lines:
            parts.append("\nWhat I read and stored locally:")
            parts.extend(f"- {c}" for c in capture_lines[:4])
            if assist.capture_ids:
                parts.append(
                    "Stored capture IDs: " + ", ".join(f"#{cid}" for cid in assist.capture_ids)
                )

        if is_learn_intent(user_message):
            parts.append(
                "\nHow to read trade charts (from fetched snippets / local chart skill):"
            )
            # Pull short teaching bullets only from snippet text we already have.
            snippet_blob = " ".join(search_lines + capture_lines).lower()
            lessons: list[str] = []
            if any(w in snippet_blob for w in ("candlestick", "candle", "ohlc", "open high low close")):
                lessons.append(
                    "Candlesticks summarize a period’s open, high, low, and close; "
                    "body = open↔close, wicks = high/low extremes."
                )
            if any(w in snippet_blob for w in ("support", "resistance")):
                lessons.append(
                    "Support/resistance are price zones where buying or selling often pauses the move."
                )
            if any(w in snippet_blob for w in ("volume",)):
                lessons.append("Volume helps confirm whether a price move has participation behind it.")
            if any(w in snippet_blob for w in ("trend", "moving average", "ema", "sma")):
                lessons.append("Trend tools (e.g. moving averages) help see direction without reacting to every tick.")
            # Always include a solid local lesson pack for chart/TradingView learn asks,
            # even when live search/capture is empty or blocked.
            topic = user_message.lower()
            if not lessons or "chart" in topic or "tradingview" in topic or "trade" in topic:
                from app.web_learning.chart_curriculum import CHART_LESSONS

                lessons = [
                    item["instructions"].split(". ")[0].rstrip(".") + "."
                    for item in CHART_LESSONS
                ]
            for i, lesson in enumerate(lessons, start=1):
                parts.append(f"{i}. {lesson}")

        if not search_lines and not capture_lines:
            parts.append(
                "\nLive web evidence was thin or unavailable this run. "
                "I still taught from the local chart-reading skill pack above. "
                "After internet is approved, ask again to store tutorial pages locally."
            )

        topic = user_message.lower()
        if "tradingview" in topic or "chart" in topic or "trade chart" in topic:
            parts.append(
                "\nI am not giving fake click-through steps for the live TradingView canvas — "
                "that chart UI is JavaScript and not readable as plain HTML. "
                "Teaching above comes from search/capture skill evidence and/or local chart skill."
            )
        return "\n".join(parts)

    def _compose_news_briefing(
        self,
        *,
        search_hits: list[dict[str, str]],
        capture_lines: list[str],
        notes: list[str],
        capture_ids: tuple[int, ...],
    ) -> str:
        """Turn search/capture evidence into a readable current-affairs briefing."""
        bullets: list[str] = []
        sources: list[str] = []

        for hit in search_hits:
            title = (hit.get("title") or "").strip()
            url = (hit.get("url") or "").strip()
            snippet = re.sub(r"\s+", " ", (hit.get("snippet") or "").strip())
            if not title:
                continue
            if _is_weak_news_hit(title, url, snippet):
                continue
            if snippet and len(snippet) >= 40:
                bullets.append(f"• {title} — {snippet[:280]}")
            else:
                bullets.append(f"• {title}")
            if url:
                sources.append(url)
            if len(bullets) >= 6:
                break

        capture_bits: list[str] = []
        for line in capture_lines[:4]:
            title_match = re.match(r"Captured #\d+:\s+(.*?)\s+\((https?://[^)]+)\)", line)
            summary_match = re.search(r"Summary:\s*(.+)$", line, re.DOTALL)
            summary = re.sub(r"\s+", " ", (summary_match.group(1) if summary_match else "").strip())
            if title_match:
                title, url = title_match.group(1).strip(), title_match.group(2).strip()
                if url and url not in sources:
                    sources.append(url)
            else:
                title = ""
            if summary.lower().startswith("headlines:"):
                for piece in summary.split(":", 1)[1].split("|"):
                    piece = piece.strip(" -•")
                    if len(piece) >= 25 and not _is_weak_news_hit(piece, "", ""):
                        capture_bits.append(f"• {piece}")
            elif summary and len(summary) >= 40 and not any(
                m in summary.lower() for m in _WEAK_NEWS_SNIPPET_MARKERS
            ):
                label = f"From {title}: " if title else ""
                capture_bits.append(f"• {label}{summary[:420]}")
            elif title and not any(m in title.lower() for m in _WEAK_NEWS_TITLE_MARKERS):
                capture_bits.append(f"• Read more on: {title}")

        # Prefer scraped page headlines when search only returned portals.
        if capture_bits and len(bullets) < 2:
            bullets = capture_bits[:6]
            capture_bits = []
        elif capture_bits:
            # Avoid duplicating the same lines under both sections.
            capture_bits = [b for b in capture_bits if b not in bullets][:6]

        parts: list[str] = [
            "Current-affairs briefing (evidence first, then thinking):",
            "",
        ]
        if bullets:
            parts.append("1) What I fetched (facts from sources)")
            parts.extend(bullets[:8])
        if capture_bits:
            parts.append("")
            parts.append("Extra notes from pages I read")
            parts.extend(capture_bits)
        if not bullets and not capture_bits:
            parts.append(
                "Search mostly returned news portals without clear article headlines. "
                "Approve internet if needed, then ask again — or ask about a specific topic "
                "(e.g. “India current affairs today” or “US politics headlines”)."
            )
            if notes:
                parts.append("Notes: " + "; ".join(notes[:3]))
        else:
            from app.web_learning.news_curriculum import (
                classify_themes,
                follow_up_questions,
                strip_bullet,
                why_it_matters,
            )

            theme_input = [strip_bullet(b) for b in (bullets or capture_bits)[:8]]
            themes = classify_themes(theme_input)
            parts.append("")
            parts.append("2) How I'm thinking (themes)")
            for theme, items in themes:
                parts.append(f"• {theme}: {len(items)} item(s)")

            parts.append("")
            parts.append("3) Why it may matter (analysis — not new facts)")
            for note in why_it_matters(themes):
                parts.append(f"• {note}")

            parts.append("")
            parts.append("4) Questions worth asking next")
            for q in follow_up_questions(themes):
                parts.append(f"• {q}")

        if sources:
            parts.append("")
            parts.append("Sources")
            for url in sources[:6]:
                parts.append(f"- {url}")
        if capture_ids:
            parts.append(
                "Stored locally as capture IDs: "
                + ", ".join(f"#{cid}" for cid in capture_ids)
            )
        return "\n".join(parts)

    def build_learning_context(self, db: Session, specialist_id: int, limit: int = 5) -> str:
        rows = db.scalars(
            select(WebCapture)
            .where(WebCapture.specialist_id == specialist_id)
            .order_by(WebCapture.id.desc())
            .limit(limit)
        ).all()
        if not rows:
            return ""

        parts: list[str] = []
        for row in reversed(list(rows)):
            parts.append(
                f"- [{row.id}] {row.title}\n"
                f"  URL: {row.url}\n"
                f"  Summary: {row.summary}\n"
                f"  Stored: {row.text_chars} chars text, {row.image_count} images, "
                f"{row.compressed_bytes} bytes compressed"
            )
        return "\n".join(parts)

    def _extract_image_urls(self, html: str, base_url: str) -> list[str]:
        found: list[str] = []
        for match in _IMG_SRC_PATTERN.finditer(html):
            src = match.group(1).strip()
            if not src or src.startswith("data:"):
                continue
            absolute = urljoin(base_url, src)
            if absolute not in found:
                found.append(absolute)
        return found

    def _write_gzip_json(self, path: Path, payload: dict) -> int:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        path.write_bytes(gzip.compress(raw, compresslevel=9))
        return path.stat().st_size

    def _read_gzip_json(self, path: Path) -> dict:
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))

    def _compress_image(self, raw: bytes, index: int) -> tuple[bytes, str]:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(raw))
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            max_side = 1280
            image.thumbnail((max_side, max_side))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=75, optimize=True)
            jpeg = buffer.getvalue()
            gz = gzip.compress(jpeg, compresslevel=9)
            return gz, f"img_{index:03d}.jpg.gz"
        except Exception:
            gz = gzip.compress(raw, compresslevel=9)
            return gz, f"img_{index:03d}.bin.gz"
