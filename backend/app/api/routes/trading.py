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
    recent_count: int = 0
    imp_notes: int = 0
    internet_approved: bool = False
    chart_skills: str = "line, bar, candle, heikin-ashi, area/baseline, volume, trend, S/R"
    notes: str = (
        "Send TradingView alerts to POST /trading/webhooks/tradingview. "
        "POST /trading/learn to Google Zerodha/TradingView and save IMP notes. "
        "Ask the trading bot about a ticker to combine chart skills + company news + saved notes."
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
        for n in _learnings.list_learnings(db, bot_slug="trading-bot", limit=50)
        if n.kind in {"trading-imp", "trading-session", "web"}
    ]
    bot = _specialists.get_by_slug(db, "trading-bot")
    return TradingStatus(
        enabled=bool(bot.enabled) if bot else False,
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
        if r.kind not in {"trading-imp", "trading-session", "web", "method"}:
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
