from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MemoryItem
from app.memory.extractor import extract_memories
from app.schemas.memory import MemoryRecord, MemorySummary


class MemoryService:
    def extract_and_store(self, db: Session, message: str) -> int:
        candidates = extract_memories(message)
        created = 0

        for candidate in candidates:
            existing = db.scalar(
                select(MemoryItem).where(
                    MemoryItem.memory_type == candidate.memory_type,
                    MemoryItem.key == candidate.key,
                    MemoryItem.value == candidate.value,
                )
            )
            if existing:
                continue

            db.add(
                MemoryItem(
                    memory_type=candidate.memory_type,
                    key=candidate.key,
                    value=candidate.value,
                    confidence=candidate.confidence,
                    source=candidate.source,
                )
            )
            created += 1

        return created

    def list_memories(self, db: Session, memory_type: str | None = None, limit: int = 100) -> list[MemoryRecord]:
        stmt = select(MemoryItem).order_by(MemoryItem.id.desc()).limit(limit)
        if memory_type:
            stmt = stmt.where(MemoryItem.memory_type == memory_type)

        rows = db.scalars(stmt).all()
        rows.reverse()
        return [
            MemoryRecord(
                id=row.id,
                memory_type=row.memory_type,
                key=row.key,
                value=row.value,
                confidence=row.confidence,
                source=row.source,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def summarize(self, db: Session) -> list[MemorySummary]:
        stmt = (
            select(MemoryItem.memory_type, func.count(MemoryItem.id))
            .group_by(MemoryItem.memory_type)
            .order_by(MemoryItem.memory_type.asc())
        )
        rows = db.execute(stmt).all()
        return [MemorySummary(memory_type=row[0], count=row[1]) for row in rows]

    def recent_context(self, db: Session, limit: int = 8) -> str:
        stmt = select(MemoryItem).order_by(MemoryItem.id.desc()).limit(limit)
        rows = db.scalars(stmt).all()
        if not rows:
            return ""
        rows.reverse()
        parts = [f"{row.memory_type}:{row.key}={row.value}" for row in rows]
        return "\n".join(parts)
