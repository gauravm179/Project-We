"""Trading webhook intake (TradingView and generic alert JSON)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR
from app.db.models import TradingWebhookEvent

logger = logging.getLogger(__name__)

WEBHOOK_DIR = DATA_DIR / "trading" / "webhooks"


@dataclass(frozen=True)
class StoredWebhook:
    id: int
    source: str
    ticker: str | None
    action: str | None
    payload: dict[str, Any]
    storage_path: str
    created_at: str


class TradingWebhookService:
    def store(
        self,
        db: Session,
        *,
        source: str,
        payload: dict[str, Any],
    ) -> StoredWebhook:
        WEBHOOK_DIR.mkdir(parents=True, exist_ok=True)
        ticker = (
            str(payload.get("ticker") or payload.get("symbol") or payload.get("Ticker") or "")
            .strip()
            .upper()
            or None
        )
        action = (
            str(
                payload.get("action")
                or payload.get("side")
                or payload.get("order")
                or payload.get("strategy.order.action")
                or ""
            ).strip()
            or None
        )
        row = TradingWebhookEvent(
            source=(source or "generic").strip()[:64] or "generic",
            ticker=ticker,
            action=action,
            payload_json=json.dumps(payload)[:20_000],
            storage_path="",
        )
        db.add(row)
        db.flush()

        path = WEBHOOK_DIR / f"{row.id}.json"
        path.write_text(
            json.dumps(
                {
                    "id": row.id,
                    "source": row.source,
                    "ticker": ticker,
                    "action": action,
                    "payload": payload,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        row.storage_path = str(path.relative_to(DATA_DIR))
        db.commit()
        db.refresh(row)
        logger.info("Stored trading webhook #%s source=%s ticker=%s", row.id, row.source, ticker)
        return StoredWebhook(
            id=row.id,
            source=row.source,
            ticker=row.ticker,
            action=row.action,
            payload=payload,
            storage_path=row.storage_path,
            created_at=row.created_at.isoformat(),
        )

    def recent(self, db: Session, *, limit: int = 20) -> list[StoredWebhook]:
        rows = db.scalars(
            select(TradingWebhookEvent).order_by(TradingWebhookEvent.id.desc()).limit(limit)
        ).all()
        out: list[StoredWebhook] = []
        for row in rows:
            try:
                payload = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            out.append(
                StoredWebhook(
                    id=row.id,
                    source=row.source,
                    ticker=row.ticker,
                    action=row.action,
                    payload=payload if isinstance(payload, dict) else {},
                    storage_path=row.storage_path,
                    created_at=row.created_at.isoformat(),
                )
            )
        return out

    def get(self, db: Session, event_id: int) -> StoredWebhook | None:
        row = db.get(TradingWebhookEvent, event_id)
        if row is None:
            return None
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        return StoredWebhook(
            id=row.id,
            source=row.source,
            ticker=row.ticker,
            action=row.action,
            payload=payload if isinstance(payload, dict) else {},
            storage_path=row.storage_path,
            created_at=row.created_at.isoformat(),
        )
