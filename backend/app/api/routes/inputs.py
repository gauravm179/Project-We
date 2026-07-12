from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.inputs.service import InputService
from app.schemas.input import InputEventRecord, ScreenInputRequest, VoiceInputRequest

router = APIRouter(prefix="/inputs", tags=["inputs"])
input_service = InputService()


@router.get("", response_model=list[InputEventRecord])
def list_input_events(
    input_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[InputEventRecord]:
    return input_service.list_events(db=db, input_type=input_type, limit=limit)


@router.post("/screen", response_model=InputEventRecord)
def ingest_screen_input(
    payload: ScreenInputRequest,
    db: Session = Depends(get_db),
) -> InputEventRecord:
    if not payload.shared:
        raise HTTPException(
            status_code=403,
            detail="Screen access denied. Set shared=true only when user explicitly shares screen.",
        )
    record = input_service.ingest_screen(db=db, content=payload.content, source=payload.source)
    db.commit()
    return record


@router.post("/voice", response_model=InputEventRecord)
def ingest_voice_input(
    payload: VoiceInputRequest,
    db: Session = Depends(get_db),
) -> InputEventRecord:
    if not payload.shared:
        raise HTTPException(
            status_code=403,
            detail="Voice access denied. Set shared=true only when user explicitly shares voice.",
        )
    record = input_service.ingest_voice(db=db, transcript=payload.transcript, source=payload.source)
    db.commit()
    return record
