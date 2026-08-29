"""Trading-bot internet learning: Google trusted sites, capture, save IMP notes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.learning.local_store import LocalLearningStore
from app.web_learning.service import CaptureResult, SearchPersistResult, WebLearningService

logger = logging.getLogger(__name__)

TRADING_BOT_SLUG = "trading-bot"

# Prefer education pages from these hosts when choosing what to capture.
TRUSTED_HOSTS: tuple[str, ...] = (
    "zerodha.com",
    "kite.zerodha.com",
    "tradingview.com",
    "investopedia.com",
    "nseindia.com",
    "moneycontrol.com",
    "groww.in",
    "angelone.in",
    "stockcharts.com",
    "babypips.com",
)

# Paths on TradingView that are readable HTML (skip live chart widgets).
_TV_OK_PATH_PREFIXES = (
    "/support/",
    "/chart-patterns/",
    "/pine-script-docs/",
    "/blog/",
    "/ideas/education",
    "/scripts/education",
)

_DEFAULT_QUERIES: tuple[str, ...] = (
    "site:zerodha.com/varsity candlestick charts technical analysis",
    "site:zerodha.com/varsity support resistance trendlines",
    "site:tradingview.com/support how to read candlestick charts",
    "site:investopedia.com candlestick patterns technical analysis guide",
    "Zerodha Varsity risk management stop loss position sizing",
)

_LEARN_ASK = re.compile(
    r"\b("
    r"learn\s+from\s+(?:the\s+)?(?:internet|web|google|online)|"
    r"learn\s+(?:from\s+)?(?:zerodha|varsity|trading\s*view|tradingview|investopedia)|"
    r"study\s+(?:zerodha|varsity|trading\s*view|tradingview)|"
    r"google\s+(?:zerodha|varsity|trading\s*view|tradingview|trading)|"
    r"train\s+(?:yourself|the\s+bot|trading[\s-]?bot).{0,40}(?:web|internet|zerodha|tradingview)|"
    r"save\s+(?:imp|important)\s+(?:data|notes|learning)|"
    r"capture\s+(?:and\s+)?(?:learn|save).{0,30}(?:zerodha|tradingview|trading)|"
    r"enable\s+(?:internet|web).{0,30}trad|"
    r"trad(?:ing)?[\s-]?bot.{0,40}learn\s+from"
    r")\b",
    re.IGNORECASE,
)

_SITE_HINTS = re.compile(
    r"\b(zerodha|varsity|trading\s*view|tradingview|investopedia|nse|groww|angel\s*one)\b",
    re.IGNORECASE,
)


@dataclass
class SavedImpNote:
    learning_id: int
    title: str
    source_url: str
    preview: str


@dataclass
class TradingWebLearnResult:
    queries: list[str] = field(default_factory=list)
    searched: int = 0
    captured: int = 0
    saved: list[SavedImpNote] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requires_permission: bool = False
    permission_request_id: int | None = None
    message: str = ""


def is_trading_web_learn_ask(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _LEARN_ASK.search(text):
        return True
    # "learn candlesticks from zerodha" / "teach tradingview support resistance"
    if re.search(r"\b(learn|teach|study|train)\b", text, re.IGNORECASE) and _SITE_HINTS.search(
        text
    ):
        return True
    return False


def build_learn_queries(user_message: str, *, limit: int = 4) -> list[str]:
    """Pick Google queries from the user ask + trusted-site defaults."""
    text = re.sub(r"\s+", " ", (user_message or "").strip())
    queries: list[str] = []
    lower = text.lower()

    topic = text
    for junk in (
        "learn from the internet",
        "learn from internet",
        "learn from web",
        "google",
        "please",
        "can you",
        "trading bot",
        "enable",
        "and save",
        "imp data",
        "important data",
        "for future",
    ):
        topic = re.sub(re.escape(junk), " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+", " ", topic).strip(" .?!")

    if "zerodha" in lower or "varsity" in lower:
        queries.append(
            f"site:zerodha.com/varsity {topic or 'technical analysis candlestick'}"
        )
    if "tradingview" in lower or "trading view" in lower:
        queries.append(
            f"site:tradingview.com/support {topic or 'candlestick chart types'}"
        )
    if "investopedia" in lower:
        queries.append(f"site:investopedia.com {topic or 'technical analysis'}")

    if not queries and topic and len(topic) >= 8:
        queries.append(f"{topic} site:zerodha.com/varsity OR site:tradingview.com/support")
        queries.append(f"{topic} technical analysis tutorial guide")

    for q in _DEFAULT_QUERIES:
        if len(queries) >= limit:
            break
        if q not in queries:
            queries.append(q)
    return queries[:limit]


def host_trusted(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS)


def url_worth_capturing(url: str) -> bool:
    """Allow education pages; skip live TradingView chart widgets."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "").lower()

    if "tradingview.com" in host:
        if any(path.startswith(p) for p in _TV_OK_PATH_PREFIXES):
            return True
        # Chart widgets / symbol pages are JS-only.
        if path.startswith("/chart") or "/x/" in path:
            return False
        return "/support" in path or "education" in path or "candlestick" in path

    if "zerodha.com" in host:
        # Varsity chapters are the main learning surface.
        return "varsity" in path or "z-connect" in path or "/blog" in path

    return host_trusted(url)


def _score_result(url: str, title: str, snippet: str) -> int:
    score = 0
    if host_trusted(url):
        score += 10
    if url_worth_capturing(url):
        score += 8
    blob = f"{title} {snippet} {url}".lower()
    for key in (
        "varsity",
        "candlestick",
        "support",
        "resistance",
        "technical analysis",
        "chart",
        "risk",
        "stop loss",
        "tutorial",
        "module",
        "chapter",
    ):
        if key in blob:
            score += 2
    if any(bad in blob for bad in ("login", "signup", "pricing plans", "download app")):
        score -= 4
    return score


def distill_imp_note(*, title: str, url: str, summary: str, query: str) -> str:
    """Compress a capture into an IMP note the bot can recall later."""
    body = (summary or "").strip()
    # Keep dense, referable bullets — not a full page dump.
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    compact: list[str] = []
    for ln in lines:
        if len(" ".join(compact)) > 1800:
            break
        compact.append(ln[:320])
    facts = "\n".join(f"• {ln}" for ln in compact[:12]) or "• (little readable text extracted)"
    return (
        f"IMP TRADING NOTE\n"
        f"Source: {title}\n"
        f"URL: {url}\n"
        f"Found via Google query: {query}\n"
        f"Why kept: trusted education / chart knowledge for future reference.\n"
        f"Key points:\n{facts}"
    )


def format_learn_reply(result: TradingWebLearnResult) -> str:
    if result.requires_permission:
        return result.message or (
            "Approve internet so trading-bot can Google Zerodha, TradingView, "
            "and other education sites, then save IMP notes locally."
        )
    parts = [
        "Trading web learning session (Google → pick trusted pages → save IMP notes):",
        "",
        f"Queries run: {result.searched}",
        f"Pages captured: {result.captured}",
        f"IMP notes saved: {len(result.saved)}",
    ]
    if result.saved:
        parts.append("")
        parts.append("Saved for future reference:")
        for note in result.saved:
            parts.append(f"• #{note.learning_id} {note.title}")
            parts.append(f"  {note.source_url}")
            if note.preview:
                parts.append(f"  {note.preview[:180]}")
    if result.skipped:
        parts.append("")
        parts.append("Skipped (not useful HTML / chart widgets):")
        for s in result.skipped[:5]:
            parts.append(f"• {s}")
    if result.errors:
        parts.append("")
        parts.append("Issues:")
        for e in result.errors[:4]:
            parts.append(f"• {e}")
    parts.append("")
    parts.append(
        "These IMP notes stay in local learnings and are recalled on later trading asks. "
        "Not financial advice — education only."
    )
    return "\n".join(parts)


async def run_trading_web_learn(
    db: Session,
    web: WebLearningService,
    *,
    user_message: str,
    max_queries: int = 3,
    max_captures: int = 3,
) -> TradingWebLearnResult:
    """Search preferred trading education sites, capture best pages, save IMP notes."""
    out = TradingWebLearnResult()
    if not web.internet_allowed(db):
        blocked = web._permission_block(  # noqa: SLF001
            db,
            "trading-bot needs internet to Google Zerodha/TradingView and save IMP notes",
        )
        out.requires_permission = True
        out.permission_request_id = int(blocked["permission_request_id"])  # type: ignore[arg-type]
        out.message = str(blocked["message"])
        return out

    store = LocalLearningStore()
    queries = build_learn_queries(user_message, limit=max_queries)
    out.queries = list(queries)
    seen_urls: set[str] = set()
    captures_left = max_captures

    for query in queries:
        try:
            search = await web.search_web(db, query, limit=6, auto_capture_top=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trading learn search failed for %r: %s", query, exc)
            out.errors.append(f"Search failed ({query[:60]}): {exc}")
            continue
        if isinstance(search, dict):
            if search.get("requires_permission"):
                out.requires_permission = True
                out.permission_request_id = search.get("permission_request_id")  # type: ignore[assignment]
                out.message = str(search.get("message") or "")
                return out
            out.errors.append(str(search.get("error") or search))
            continue
        if not isinstance(search, SearchPersistResult):
            continue
        out.searched += 1

        ranked = sorted(
            search.results,
            key=lambda r: _score_result(r.url, r.title, r.snippet),
            reverse=True,
        )
        for result in ranked:
            if captures_left <= 0:
                break
            url = (result.url or "").strip()
            if not url or url in seen_urls:
                continue
            if not url_worth_capturing(url):
                out.skipped.append(f"{result.title[:80]} — {url[:120]}")
                continue
            if _score_result(url, result.title, result.snippet) < 10:
                out.skipped.append(f"low score: {result.title[:80]}")
                continue
            seen_urls.add(url)
            try:
                captured = await web.capture_url(
                    db,
                    "web-learner-bot",
                    url,
                    max_images=1,
                    allow_without_permission=True,
                )
            except Exception as exc:  # noqa: BLE001
                out.errors.append(f"Capture failed {url[:80]}: {exc}")
                continue
            if isinstance(captured, dict):
                out.errors.append(str(captured.get("error") or captured))
                continue
            if not isinstance(captured, CaptureResult):
                continue
            out.captured += 1
            captures_left -= 1
            note_body = distill_imp_note(
                title=captured.title or result.title,
                url=captured.url or url,
                summary=captured.summary or result.snippet,
                query=query,
            )
            # Skip empty shells
            if len((captured.summary or "").strip()) < 80 and len(result.snippet or "") < 40:
                out.skipped.append(f"too little text: {url[:120]}")
                continue
            learning = store.record(
                db,
                bot_slug=TRADING_BOT_SLUG,
                kind="trading-imp",
                title=(captured.title or result.title or "Trading IMP note")[:200],
                content=note_body,
                source_ref=f"capture:{captured.capture_id}|{url}"[:250],
                shared=True,
            )
            out.saved.append(
                SavedImpNote(
                    learning_id=learning.id,
                    title=learning.title,
                    source_url=url,
                    preview=(captured.summary or result.snippet or "")[:220],
                )
            )

    # Session index note for quick recall
    if out.saved:
        index = (
            "TRADING WEB LEARN SESSION\n"
            f"Queries: {', '.join(out.queries)}\n"
            f"Saved IMP ids: {', '.join(str(s.learning_id) for s in out.saved)}\n"
            "Sources:\n"
            + "\n".join(f"- {s.title} ({s.source_url})" for s in out.saved)
        )
        store.record(
            db,
            bot_slug=TRADING_BOT_SLUG,
            kind="trading-session",
            title="Trading web learn session",
            content=index[:4000],
            source_ref="trading-web-learn",
            shared=True,
        )
    elif not out.errors and not out.requires_permission:
        out.errors.append(
            "No capturable education pages found this round. "
            "Try: “learn from Zerodha Varsity candlesticks” or approve internet and retry."
        )
    return out
