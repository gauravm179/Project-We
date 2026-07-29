from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Skill, SkillAssignment, Specialist
from app.schemas.skill import (
    SkillAssignmentRecord,
    SkillAssignmentUpdate,
    SkillCreate,
    SkillLearnRequest,
    SkillRecord,
)

logger = logging.getLogger(__name__)


def _skill_to_record(row: Skill) -> SkillRecord:
    return SkillRecord(
        id=row.id,
        slug=row.slug,
        name=row.name,
        category=row.category,
        description=row.description,
        instructions=row.instructions,
        parameters_schema=json.loads(row.parameters_schema),
        created_at=row.created_at,
    )


def _assignment_to_record(a: SkillAssignment, skill: Skill) -> SkillAssignmentRecord:
    return SkillAssignmentRecord(
        id=a.id,
        skill_slug=skill.slug,
        skill_name=skill.name,
        category=skill.category,
        status=a.status,
        parameters=json.loads(a.parameters),
        instructions=skill.instructions,
        learned_at=a.learned_at,
        activated_at=a.activated_at,
    )


class SkillService:

    def create_skill(self, db: Session, payload: SkillCreate) -> SkillRecord | None:
        row = Skill(
            slug=payload.slug,
            name=payload.name,
            category=payload.category,
            description=payload.description,
            instructions=payload.instructions,
            parameters_schema=json.dumps(payload.parameters_schema),
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        db.refresh(row)
        logger.info("Created skill %s (%s)", row.slug, row.category)
        return _skill_to_record(row)

    def list_skills(self, db: Session) -> list[SkillRecord]:
        rows = db.scalars(select(Skill).order_by(Skill.id)).all()
        return [_skill_to_record(r) for r in rows]

    def get_skill(self, db: Session, slug: str) -> SkillRecord | None:
        row = db.scalar(select(Skill).where(Skill.slug == slug))
        return _skill_to_record(row) if row else None

    def learn_skill(
        self,
        db: Session,
        specialist_slug: str | None,
        payload: SkillLearnRequest,
    ) -> SkillAssignmentRecord | None:
        skill = db.scalar(select(Skill).where(Skill.slug == payload.skill_slug))
        if not skill:
            return None

        specialist_id: int | None = None
        if specialist_slug:
            specialist = db.scalar(
                select(Specialist).where(Specialist.slug == specialist_slug)
            )
            if not specialist:
                return None
            specialist_id = specialist.id

        assignment = SkillAssignment(
            skill_id=skill.id,
            specialist_id=specialist_id,
            status="learning",
            parameters=json.dumps(payload.parameters),
        )
        db.add(assignment)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None
        db.refresh(assignment)
        logger.info(
            "Specialist %s is learning skill %s",
            specialist_slug or "main-bot",
            skill.slug,
        )
        return _assignment_to_record(assignment, skill)

    def activate_skill(
        self, db: Session, assignment_id: int
    ) -> SkillAssignmentRecord | None:
        a = db.scalar(select(SkillAssignment).where(SkillAssignment.id == assignment_id))
        if not a:
            return None
        a.status = "active"
        a.activated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(a)
        skill = db.scalar(select(Skill).where(Skill.id == a.skill_id))
        return _assignment_to_record(a, skill)  # type: ignore[arg-type]

    def update_assignment(
        self, db: Session, assignment_id: int, patch: SkillAssignmentUpdate
    ) -> SkillAssignmentRecord | None:
        a = db.scalar(select(SkillAssignment).where(SkillAssignment.id == assignment_id))
        if not a:
            return None
        if patch.status is not None:
            a.status = patch.status
            if patch.status == "active" and a.activated_at is None:
                a.activated_at = datetime.now(timezone.utc)
        if patch.parameters is not None:
            a.parameters = json.dumps(patch.parameters)
        db.commit()
        db.refresh(a)
        skill = db.scalar(select(Skill).where(Skill.id == a.skill_id))
        return _assignment_to_record(a, skill)  # type: ignore[arg-type]

    def list_assignments(
        self, db: Session, specialist_slug: str | None
    ) -> list[SkillAssignmentRecord]:
        if specialist_slug:
            specialist = db.scalar(
                select(Specialist).where(Specialist.slug == specialist_slug)
            )
            if not specialist:
                return []
            stmt = select(SkillAssignment).where(
                SkillAssignment.specialist_id == specialist.id
            )
        else:
            stmt = select(SkillAssignment).where(SkillAssignment.specialist_id.is_(None))

        assignments = db.scalars(stmt.order_by(SkillAssignment.id)).all()
        result: list[SkillAssignmentRecord] = []
        for a in assignments:
            skill = db.scalar(select(Skill).where(Skill.id == a.skill_id))
            if skill:
                result.append(_assignment_to_record(a, skill))
        return result

    def build_skill_context(self, db: Session, specialist_id: int | None) -> str:
        """Build a text block summarizing all active skills for injection into prompts."""
        stmt = (
            select(SkillAssignment)
            .where(SkillAssignment.status == "active")
            .order_by(SkillAssignment.id)
        )
        if specialist_id is not None:
            stmt = stmt.where(SkillAssignment.specialist_id == specialist_id)
        else:
            stmt = stmt.where(SkillAssignment.specialist_id.is_(None))

        assignments = db.scalars(stmt).all()
        if not assignments:
            return ""

        parts: list[str] = []
        for a in assignments:
            skill = db.scalar(select(Skill).where(Skill.id == a.skill_id))
            if not skill:
                continue
            params = json.loads(a.parameters)
            param_text = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "none"
            parts.append(
                f"[SKILL: {skill.name}] ({skill.category})\n"
                f"Parameters: {param_text}\n"
                f"Instructions: {skill.instructions}"
            )

        return "\n\n".join(parts)
