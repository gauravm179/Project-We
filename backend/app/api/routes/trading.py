from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.specialists.service import SpecialistService
from app.trading.intent import format_webhook_as_user_message
from app.trading.webhooks import TradingWebhookService

router = APIRouter(prefix="/trading", tags=["trading"])
_webhooks = TradingWebhookService()
_specialists = SpecialistService()


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
    webhook_url: str = "/trading/webhooks/tradingview"
    recent_count: int = 0
    chart_skills: str = "line, bar, candle, heikin-ashi, area/baseline, volume, trend, S/R"
    notes: str = (
        "Send TradingView alerts to POST /trading/webhooks/tradingview. "
        "Ask the trading bot about a ticker to combine chart skills + company news."
    )


@router.get("/status", response_model=TradingStatus)
def trading_status(db: Session = Depends(get_db)) -> TradingStatus:
    recent = _webhooks.recent(db, limit=5)
    return TradingStatus(recent_count=len(recent))


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
