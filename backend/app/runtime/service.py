from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Heartbeat
from app.schemas.runtime import HeartbeatRecord, RuntimeStatus

logger = logging.getLogger(__name__)

_start_time: float = time.monotonic()
_started_at: datetime = datetime.now(timezone.utc)


def reset_start_time() -> None:
    """Reset the process start time (useful for tests)."""
    global _start_time, _started_at  # noqa: PLW0603
    _start_time = time.monotonic()
    _started_at = datetime.now(timezone.utc)


class RuntimeService:

    def uptime_seconds(self) -> float:
        return time.monotonic() - _start_time

    def record_heartbeat(self, db: Session) -> HeartbeatRecord:
        hb = Heartbeat(
            uptime_seconds=self.uptime_seconds(),
            status="healthy",
        )
        db.add(hb)
        db.commit()
        db.refresh(hb)
        return HeartbeatRecord(
            id=hb.id,
            uptime_seconds=hb.uptime_seconds,
            status=hb.status,
            recorded_at=hb.recorded_at,
        )

    def status(self, db: Session) -> RuntimeStatus:
        count = db.scalar(select(func.count(Heartbeat.id))) or 0
        last = db.scalar(
            select(Heartbeat).order_by(Heartbeat.id.desc()).limit(1)
        )
        return RuntimeStatus(
            status="running",
            uptime_seconds=self.uptime_seconds(),
            started_at=_started_at,
            last_heartbeat=last.recorded_at if last else None,
            heartbeat_count=count,
        )

    def recent_heartbeats(self, db: Session, limit: int = 20) -> list[HeartbeatRecord]:
        rows = db.scalars(
            select(Heartbeat).order_by(Heartbeat.id.desc()).limit(limit)
        ).all()
        rows.reverse()
        return [
            HeartbeatRecord(
                id=r.id,
                uptime_seconds=r.uptime_seconds,
                status=r.status,
                recorded_at=r.recorded_at,
            )
            for r in rows
        ]


async def heartbeat_loop(
    session_factory,
    interval_seconds: float = 60.0,
) -> None:
    """Background coroutine that records heartbeats at a fixed interval."""
    service = RuntimeService()
    while True:
        await asyncio.sleep(interval_seconds)
        db = session_factory()
        try:
            service.record_heartbeat(db)
            logger.debug("Heartbeat recorded, uptime=%.0fs", service.uptime_seconds())
        except Exception:
            logger.exception("Failed to record heartbeat")
        finally:
            db.close()
