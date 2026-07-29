from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.runtime.service import RuntimeService
from app.schemas.runtime import HeartbeatRecord, RuntimeStatus

router = APIRouter(prefix="/runtime", tags=["runtime"])
_service = RuntimeService()


@router.get("/status", response_model=RuntimeStatus)
def runtime_status(db: Session = Depends(get_db)):
    return _service.status(db)


@router.post("/heartbeat", response_model=HeartbeatRecord, status_code=201)
def manual_heartbeat(db: Session = Depends(get_db)):
    """Manually trigger a heartbeat (automatic ones run in background)."""
    return _service.record_heartbeat(db)


@router.get("/heartbeats", response_model=list[HeartbeatRecord])
def recent_heartbeats(limit: int = 20, db: Session = Depends(get_db)):
    return _service.recent_heartbeats(db, limit)
