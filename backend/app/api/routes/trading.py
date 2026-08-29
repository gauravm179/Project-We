from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.learning.local_store import LocalLearningStore
from app.policy.service import PolicyService
from app.specialists.service import SpecialistService
from app.trading.intent import format_webhook_as_user_message
from app.trading.ta_curriculum import TA_TOPICS, install_ta_kb_local
from app.trading.ta_kb import format_full_ta_reply, install_full_ta_kb
from app.trading.web_learn import format_learn_reply, run_trading_web_learn
from app.trading.webhooks import TradingWebhookService
from app.web_learning.service import WebLearningService

router = APIRouter(prefix="/trading", tags=["trading"])
_webhooks = TradingWebhookService()
_specialists = SpecialistService()
_web = WebLearningService()
_learnings = LocalLearningStore()


class TradingWebhookResponse(BaseModel):
    id: int
    source: str
    ticker: str | None = None
    action: str | None = None
    storage_path: str
    analysis: str | None = None
    message: str


class TradingWebhookListItem(BaseModel):
    id: int
    source: str
    ticker: str | None = None
    action: str | None = None
    created_at: str


class TradingStatus(BaseModel):
    bot: str = "trading-bot"
    enabled: bool = True
    webhook_url: str = "/trading/webhooks/tradingview"
    learn_url: str = "/trading/learn"
    ta_kb_url: str = "/trading/install-ta-kb"
    ta_kb_topics: int = 0
    recent_count: int = 0
    imp_notes: int = 0
    internet_approved: bool = False
    chart_skills: str = (
        "line, bar, candle, HA, renko, kagi, P&F, range, patterns, indicators, scenarios"
    )
    notes: str = (
        "POST /trading/install-ta-kb for full local TA database (all chart types + technicals). "
        "POST /trading/learn to fetch TradingView/Zerodha pages. "
        "POST /trading/webhooks/tradingview for alerts."
    )


class TradingLearnRequest(BaseModel):
    message: str = Field(
        default="learn from Zerodha Varsity and TradingView candlestick charts",
        min_length=3,
        max_length=500,
    )


class TradingLearnResponse(BaseModel):
    searched: int
    captured: int
    saved_count: int
    requires_permission: bool = False
    permission_request_id: int | None = None
    reply: str
    saved: list[dict[str, Any]] = Field(default_factory=list)


class TradingTaKbResponse(BaseModel):
    topic_count: int
    categories: list[str] = Field(default_factory=list)
    web_saved: int = 0
    requires_permission: bool = False
    permission_request_id: int | None = None
    reply: str


class TradingLearningItem(BaseModel):
    id: int
    kind: str
    title: str
    preview: str
    source_ref: str | None = None
    created_at: str


@router.get("/status", response_model=TradingStatus)
def trading_status(db: Session = Depends(get_db)) -> TradingStatus:
    recent = _webhooks.recent(db, limit=5)
    notes = [
        n
        for n in _learnings.list_learnings(db, bot_slug="trading-bot", limit=100)
        if n.kind in {"trading-imp", "trading-session", "web", "ta-kb"}
    ]
    bot = _specialists.get_by_slug(db, "trading-bot")
    return TradingStatus(
        enabled=bool(bot.enabled) if bot else False,
        ta_kb_topics=len(TA_TOPICS),
        recent_count=len(recent),
        imp_notes=len(notes),
        internet_approved=PolicyService().has_approved_capability(db, "internet"),
    )


@router.get("/learnings", response_model=list[TradingLearningItem])
def list_trading_learnings(
    limit: int = 20, db: Session = Depends(get_db)
) -> list[TradingLearningItem]:
    rows = _learnings.list_learnings(db, bot_slug="trading-bot", limit=min(max(limit, 1), 100))
    out: list[TradingLearningItem] = []
    for r in reversed(rows):
        if r.kind not in {"trading-imp", "trading-session", "web", "method", "ta-kb"}:
            continue
        created = r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at)
        out.append(
            TradingLearningItem(
                id=r.id,
                kind=r.kind,
                title=r.title,
                preview=(r.content or "")[:240],
                source_ref=r.source_ref,
                created_at=created,
            )
        )
        if len(out) >= limit:
            break
    return out


@router.post("/learn", response_model=TradingLearnResponse)
async def trading_learn(
    payload: TradingLearnRequest | None = None,
    db: Session = Depends(get_db),
) -> TradingLearnResponse:
    """Google trusted trading education sites, capture pages, save IMP notes."""
    message = (payload.message if payload else None) or (
        "learn from Zerodha Varsity and TradingView candlestick charts"
    )
    result = await run_trading_web_learn(
        db,
        _web,
        user_message=message,
        max_queries=3,
        max_captures=3,
    )
    return TradingLearnResponse(
        searched=result.searched,
        captured=result.captured,
        saved_count=len(result.saved),
        requires_permission=result.requires_permission,
        permission_request_id=result.permission_request_id,
        reply=format_learn_reply(result),
        saved=[
            {
                "id": s.learning_id,
                "title": s.title,
                "url": s.source_url,
                "preview": s.preview,
            }
            for s in result.saved
        ],
    )


@router.post("/install-ta-kb", response_model=TradingTaKbResponse)
async def install_ta_kb(
    fetch_web: bool = True,
    db: Session = Depends(get_db),
) -> TradingTaKbResponse:
    """Install full local TA KB (all chart types, patterns, indicators, scenarios)."""
    internet = PolicyService().has_approved_capability(db, "internet")
    local, web_result = await install_full_ta_kb(
        db,
        _web,
        fetch_web=fetch_web and internet,
    )
    reply = format_full_ta_reply(local, web_result, internet_approved=internet)
    return TradingTaKbResponse(
        topic_count=int(local.get("topic_count") or 0),
        categories=[str(c) for c in (local.get("categories") or [])],
        web_saved=len(web_result.saved) if web_result else 0,
        requires_permission=bool(web_result and web_result.requires_permission),
        permission_request_id=(
            web_result.permission_request_id if web_result else None
        ),
        reply=reply,
    )


@router.post("/install-ta-kb/local", response_model=TradingTaKbResponse)
def install_ta_kb_local_only(db: Session = Depends(get_db)) -> TradingTaKbResponse:
    """Offline-only TA KB install (no internet)."""
    local = install_ta_kb_local(db)
    reply = format_full_ta_reply(local, None, internet_approved=False)
    return TradingTaKbResponse(
        topic_count=int(local.get("topic_count") or 0),
        categories=[str(c) for c in (local.get("categories") or [])],
        reply=reply,
    )


@router.get("/webhooks/recent", response_model=list[TradingWebhookListItem])
def list_webhooks(limit: int = 20, db: Session = Depends(get_db)) -> list[TradingWebhookListItem]:
    rows = _webhooks.recent(db, limit=min(max(limit, 1), 100))
    return [
        TradingWebhookListItem(
            id=r.id,
            source=r.source,
            ticker=r.ticker,
            action=r.action,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/webhooks/tradingview", response_model=TradingWebhookResponse)
async def tradingview_webhook(
    request: Request,
    analyze: bool = True,
    db: Session = Depends(get_db),
) -> TradingWebhookResponse:
    """Receive TradingView alert webhooks (JSON body)."""
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return await _ingest(db, source="tradingview", payload=payload, analyze=analyze)


@router.post("/webhooks/{source}", response_model=TradingWebhookResponse)
async def generic_webhook(
    source: str,
    request: Request,
    analyze: bool = True,
    db: Session = Depends(get_db),
) -> TradingWebhookResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return await _ingest(db, source=source, payload=payload, analyze=analyze)


async def _ingest(
    db: Session,
    *,
    source: str,
    payload: dict[str, Any],
    analyze: bool,
) -> TradingWebhookResponse:
    stored = _webhooks.store(db, source=source, payload=payload)
    analysis: str | None = None
    if analyze:
        prompt = format_webhook_as_user_message(payload)
        reply = await _specialists.chat(db, "trading-bot", prompt)
        if reply is not None:
            analysis = reply.response
    return TradingWebhookResponse(
        id=stored.id,
        source=stored.source,
        ticker=stored.ticker,
        action=stored.action,
        storage_path=stored.storage_path,
        analysis=analysis,
        message="Webhook stored"
        + (" and analyzed by trading-bot" if analysis else " (analysis skipped)"),
    )
