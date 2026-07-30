from __future__ import annotations

import gzip
import io
import json
import logging
import re
from dataclasses import dataclass
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
    is_valid_http_url,
    message_needs_web_assist,
)
from app.web_learning.search import SearchResult, WebSearchClient

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
            return WebAssistResult(
                context="",
                requires_permission=True,
                permission_request_id=int(blocked["permission_request_id"]),  # type: ignore[arg-type]
                message=str(blocked["message"]),
            )

        parts: list[str] = [
            f"WEB LEARNER ASSIST for {requesting_bot} (via web-learner-bot):"
        ]
        capture_ids: list[int] = []
        search_id: int | None = None

        if auto_search:
            query = extract_search_query(message)
            if query:
                try:
                    search = await self.search_web(db, query, limit=5)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Web search failed for %r: %s", query, exc)
                    parts.append(f"Search failed ({query}): {exc}")
                    search = None
                if isinstance(search, dict):
                    return search
                if isinstance(search, SearchPersistResult):
                    search_id = search.search_id
                    parts.append(f"Search #{search.search_id} ({search.engine}): {search.query}")
                    for idx, result in enumerate(search.results, start=1):
                        parts.append(
                            f"{idx}. {result.title}\n   URL: {result.url}\n   {result.snippet}"
                        )

        if auto_capture_urls:
            for url in extract_urls(message)[:max_url_captures]:
                if not is_valid_http_url(url):
                    continue
                if _is_js_heavy_url(url):
                    parts.append(
                        f"Skipped capture of interactive chart page ({url}). "
                        "Live chart apps are JavaScript-only; use search results / tutorials instead."
                    )
                    continue
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
                    parts.append(f"Capture failed for {url}: {exc}")
                    continue
                if isinstance(captured, CaptureResult):
                    capture_ids.append(captured.capture_id)
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

        timeout = httpx.Timeout(12.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "ProjectWe-WebLearner/0.3"})
            response.raise_for_status()
            html = response.text
            content_type = response.headers.get("content-type", "")

        if "html" not in content_type and not html.lstrip().startswith("<"):
            return {"error": "URL did not return HTML content"}

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else url

        parser = _TextExtractor()
        parser.feed(html)
        page_text = parser.text()

        image_urls = self._extract_image_urls(html, base_url=url)[:max_images]

        row = WebCapture(
            specialist_id=specialist.id,
            url=url,
            title=title[:500],
            summary=page_text[:500],
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
            summary=page_text[:280] + ("..." if len(page_text) > 280 else ""),
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
