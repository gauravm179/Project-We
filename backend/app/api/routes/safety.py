from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.safety.service import SafetyService
from app.schemas.safety import SafetyStatus, SosTriggerRequest

router = APIRouter(prefix="/safety", tags=["safety"])
safety_service = SafetyService()


@router.get("/status", response_model=SafetyStatus)
def safety_status(db: Session = Depends(get_db)) -> SafetyStatus:
    return safety_service.status(db=db)


@router.post("/sos/trigger", response_model=SafetyStatus)
def trigger_sos(payload: SosTriggerRequest, db: Session = Depends(get_db)) -> SafetyStatus:
    status = safety_service.trigger_sos(db=db, reason=payload.reason)
    db.commit()
    return status
