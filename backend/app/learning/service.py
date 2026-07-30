from __future__ import annotations

from re import IGNORECASE, compile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CodingLesson, Specialist
from app.schemas.learning import MistakeFeedbackRequest, MistakeLessonRecord

_STUCK_PATTERN = compile(
    r"\b(i'?m stuck|stuck|not sure|unsure|confused|wrong again|"
    r"official (docs|documentation|guideline|standard)|best practice|"
    r"according to (pep|mdn|rfc|docs)|look up|search (the )?web|"
    r"internet guideline|latest (docs|api|guideline))\b",
    IGNORECASE,
)

_LIVE_INTERNET_PATTERN = compile(
    r"\b(latest|live|online|internet|fetch docs|search (the )?web|look up online)\b",
    IGNORECASE,
)


class LearningService:
    def message_looks_stuck_or_needs_guidelines(self, message: str) -> bool:
        return bool(_STUCK_PATTERN.search(message))

    def message_requests_live_internet(self, message: str) -> bool:
        return bool(_LIVE_INTERNET_PATTERN.search(message))

    def record_mistake(
        self,
        db: Session,
        specialist_slug: str,
        payload: MistakeFeedbackRequest,
    ) -> MistakeLessonRecord | None:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == specialist_slug))
        if specialist is None:
            return None

        row = CodingLesson(
            specialist_id=specialist.id,
            mistake=payload.mistake.strip(),
            correction=payload.correction.strip(),
            language=(payload.language or "").strip() or None,
            topic=(payload.topic or "").strip() or None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        # Mirror into shared local learning store so all bots can reuse it.
        from app.learning.local_store import LocalLearningStore

        LocalLearningStore().record(
            db,
            bot_slug=specialist.slug,
            kind="lesson",
            title=f"Correction: {(payload.topic or payload.language or 'coding')}",
            content=f"Mistake: {payload.mistake.strip()}\nCorrection: {payload.correction.strip()}",
            source_ref=f"coding_lesson:{row.id}",
            shared=True,
        )
        return self._to_record(row, specialist.slug)

    def list_lessons(
        self,
        db: Session,
        specialist_slug: str,
        limit: int = 50,
    ) -> list[MistakeLessonRecord]:
        specialist = db.scalar(select(Specialist).where(Specialist.slug == specialist_slug))
        if specialist is None:
            return []

        rows = db.scalars(
            select(CodingLesson)
            .where(CodingLesson.specialist_id == specialist.id)
            .order_by(CodingLesson.id.desc())
            .limit(limit)
        ).all()
        rows = list(rows)
        rows.reverse()
        return [self._to_record(row, specialist.slug) for row in rows]

    def build_lesson_context(self, db: Session, specialist_id: int, limit: int = 8) -> str:
        rows = db.scalars(
            select(CodingLesson)
            .where(CodingLesson.specialist_id == specialist_id)
            .order_by(CodingLesson.id.desc())
            .limit(limit)
        ).all()
        if not rows:
            return ""

        parts: list[str] = []
        for row in reversed(list(rows)):
            lang = f" [{row.language}]" if row.language else ""
            topic = f" ({row.topic})" if row.topic else ""
            parts.append(
                f"- Mistake{lang}{topic}: {row.mistake}\n"
                f"  Correction: {row.correction}"
            )
        return "\n".join(parts)

    def _to_record(self, row: CodingLesson, specialist_slug: str) -> MistakeLessonRecord:
        return MistakeLessonRecord(
            id=row.id,
            specialist_slug=specialist_slug,
            mistake=row.mistake,
            correction=row.correction,
            language=row.language,
            topic=row.topic,
            created_at=row.created_at,
        )
