from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.memory.service import MemoryService
from app.schemas.memory import MemoryRecord, MemorySummary

router = APIRouter(prefix="/memory", tags=["memory"])
memory_service = MemoryService()


@router.get("", response_model=list[MemoryRecord])
def list_memories(
    memory_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[MemoryRecord]:
    return memory_service.list_memories(db=db, memory_type=memory_type, limit=limit)


@router.get("/summary", response_model=list[MemorySummary])
def memory_summary(db: Session = Depends(get_db)) -> list[MemorySummary]:
    return memory_service.summarize(db=db)
