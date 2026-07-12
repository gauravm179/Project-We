from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.control.service import ControlService
from app.db.session import get_db
from app.schemas.control import (
    AssistRequest,
    AssistResponse,
    ControlActionCreate,
    ControlActionDecision,
    ControlActionRecord,
    ControlSessionCreate,
    ControlSessionRecord,
)

router = APIRouter(prefix="/control", tags=["control"])
control_service = ControlService()


@router.post("/sessions", response_model=ControlSessionRecord)
def create_session(payload: ControlSessionCreate, db: Session = Depends(get_db)) -> ControlSessionRecord:
    try:
        record = control_service.create_session(
            db=db,
            shared=payload.shared,
            purpose=payload.purpose,
            allow_write=payload.allow_write,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    db.commit()
    return record


@router.get("/sessions", response_model=list[ControlSessionRecord])
def list_sessions(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ControlSessionRecord]:
    return control_service.list_sessions(db=db, status=status)


@router.post("/sessions/{session_id}/end", response_model=ControlSessionRecord)
def end_session(session_id: int, db: Session = Depends(get_db)) -> ControlSessionRecord:
    record = control_service.end_session(db=db, session_id=session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Control session not found")
    db.commit()
    return record


@router.post("/sessions/{session_id}/assist", response_model=AssistResponse)
async def assist_from_screen_context(
    session_id: int,
    payload: AssistRequest,
    db: Session = Depends(get_db),
) -> AssistResponse:
    response = await control_service.assist_with_screen_context(
        db=db,
        session_id=session_id,
        task=payload.task,
        instruction=payload.instruction,
        screen_context=payload.screen_context,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Active control session not found")
    db.commit()
    return response


@router.post("/actions", response_model=ControlActionRecord)
def create_action(payload: ControlActionCreate, db: Session = Depends(get_db)) -> ControlActionRecord:
    try:
        record = control_service.create_action(
            db=db,
            session_id=payload.session_id,
            action_type=payload.action_type,
            target=payload.target,
            payload=payload.payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Active control session not found")
    db.commit()
    return record


@router.get("/actions", response_model=list[ControlActionRecord])
def list_actions(
    session_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ControlActionRecord]:
    return control_service.list_actions(db=db, session_id=session_id)


@router.post("/actions/{action_id}/decision", response_model=ControlActionRecord)
def decide_action(
    action_id: int,
    payload: ControlActionDecision,
    db: Session = Depends(get_db),
) -> ControlActionRecord:
    record = control_service.decide_action(db=db, action_id=action_id, approve=payload.approve)
    if record is None:
        raise HTTPException(status_code=404, detail="Control action not found")
    db.commit()
    return record


@router.post("/actions/{action_id}/execute", response_model=ControlActionRecord)
def execute_action(action_id: int, db: Session = Depends(get_db)) -> ControlActionRecord:
    try:
        record = control_service.execute_action(db=db, action_id=action_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Control action not found")
    db.commit()
    return record

