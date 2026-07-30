from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.learning.local_store import LocalLearningStore
from app.schemas.learning_store import LearningCreate, LearningRecordOut

router = APIRouter(prefix="/learnings", tags=["learnings"])
_store = LocalLearningStore()


@router.get("", response_model=list[LearningRecordOut])
def list_learnings(
    bot_slug: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[LearningRecordOut]:
    rows = _store.list_learnings(db, bot_slug=bot_slug, limit=limit)
    return [LearningRecordOut(**row.__dict__) for row in rows]


@router.post("", response_model=LearningRecordOut)
def create_learning(
    payload: LearningCreate,
    db: Session = Depends(get_db),
) -> LearningRecordOut:
    row = _store.record(
        db,
        bot_slug=payload.bot_slug,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        source_ref=payload.source_ref,
        shared=payload.shared,
    )
    return LearningRecordOut(**row.__dict__)
