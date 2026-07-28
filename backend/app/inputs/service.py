from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LiveInputEvent
from app.memory.service import MemoryService
from app.schemas.input import InputEventRecord


class InputService:
    def __init__(self) -> None:
        self._memory_service = MemoryService()

    def ingest_screen(self, db: Session, content: str, source: str | None) -> InputEventRecord:
        row = LiveInputEvent(input_type="screen", content=content, source=source)
        db.add(row)
        db.flush()
        self._memory_service.extract_and_store(db=db, message=content)
        return self._to_record(row)

    def ingest_voice(self, db: Session, transcript: str, source: str | None) -> InputEventRecord:
        row = LiveInputEvent(input_type="voice", content=transcript, source=source)
        db.add(row)
        db.flush()
        self._memory_service.extract_and_store(db=db, message=transcript)
        return self._to_record(row)

    def list_events(self, db: Session, input_type: str | None = None, limit: int = 100) -> list[InputEventRecord]:
        stmt = select(LiveInputEvent).order_by(LiveInputEvent.id.desc()).limit(limit)
        if input_type:
            stmt = stmt.where(LiveInputEvent.input_type == input_type)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [self._to_record(row) for row in rows]

    def _to_record(self, row: LiveInputEvent) -> InputEventRecord:
        return InputEventRecord(
            id=row.id,
            input_type=row.input_type,
            content=row.content,
            source=row.source,
            created_at=row.created_at,
        )
