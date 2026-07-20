from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.core.config import get_settings
from app.db.models import Specialist, SpecialistMessage
from app.memory.service import MemoryService
from app.schemas.specialist import (
    SpecialistChatReply,
    SpecialistCreate,
    SpecialistMessageRecord,
    SpecialistRecord,
    SpecialistUpdate,
)
from app.skills.service import SkillService

logger = logging.getLogger(__name__)


def _to_record(row: Specialist) -> SpecialistRecord:
    return SpecialistRecord(
        id=row.id,
        slug=row.slug,
        name=row.name,
        sector=row.sector,
        system_prompt=row.system_prompt,
        description=row.description,
        enabled=row.enabled,
        created_at=row.created_at,
    )


class SpecialistService:
    def __init__(self) -> None:
        self._memory = MemoryService()
        self._skills = SkillService()

    def create(self, db: Session, payload: SpecialistCreate) -> SpecialistRecord | None:
        row = Specialist(
            slug=payload.slug,
            name=payload.name,
            sector=payload.sector,
            system_prompt=payload.system_prompt,
            description=payload.description,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        db.refresh(row)
        logger.info("Created specialist %s (%s)", row.slug, row.sector)
        return _to_record(row)

    def list_all(self, db: Session) -> list[SpecialistRecord]:
        rows = db.scalars(select(Specialist).order_by(Specialist.id)).all()
        return [_to_record(r) for r in rows]

    def get_by_slug(self, db: Session, slug: str) -> SpecialistRecord | None:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        return _to_record(row) if row else None

    def update(self, db: Session, slug: str, patch: SpecialistUpdate) -> SpecialistRecord | None:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        if not row:
            return None
        if patch.name is not None:
            row.name = patch.name
        if patch.system_prompt is not None:
            row.system_prompt = patch.system_prompt
        if patch.description is not None:
            row.description = patch.description
        if patch.enabled is not None:
            row.enabled = patch.enabled
        db.commit()
        db.refresh(row)
        return _to_record(row)

    def delete(self, db: Session, slug: str) -> bool:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True

    async def chat(
        self, db: Session, slug: str, user_message: str, model_override: str | None = None
    ) -> SpecialistChatReply | None:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        if not row or not row.enabled:
            return None

        db.add(SpecialistMessage(specialist_id=row.id, role="user", content=user_message))
        db.flush()

        self._memory.extract_and_store(db=db, message=user_message)

        settings = get_settings()
        provider = build_provider(settings, model_override=model_override)
        memory_context = self._memory.recent_context(db=db)

        skill_context = self._skills.build_skill_context(db, specialist_id=row.id)
        full_prompt = row.system_prompt
        if skill_context:
            full_prompt += "\n\n--- LEARNED SKILLS ---\n" + skill_context

        assistant_text = await provider.generate(
            user_message,
            memory_context=memory_context,
            system_prompt=full_prompt,
        )

        db.add(SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text))
        db.commit()

        return SpecialistChatReply(
            specialist_slug=row.slug,
            specialist_name=row.name,
            response=assistant_text,
        )

    def history(
        self, db: Session, slug: str, limit: int = 50
    ) -> list[SpecialistMessageRecord] | None:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        if not row:
            return None

        msgs = db.scalars(
            select(SpecialistMessage)
            .where(SpecialistMessage.specialist_id == row.id)
            .order_by(SpecialistMessage.id.desc())
            .limit(limit)
        ).all()
        msgs.reverse()
        return [
            SpecialistMessageRecord(role=m.role, content=m.content, created_at=m.created_at)
            for m in msgs
        ]
