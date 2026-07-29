from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Skill, SkillAssignment, Specialist
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.schemas.specialist import SpecialistCreate, SpecialistUpdate
from app.skills.service import SkillService
from app.specialists.service import SpecialistService

logger = logging.getLogger(__name__)


def train_specialist(
    db: Session,
    bot: SpecialistCreate,
    skills: tuple[SkillCreate, ...],
    skill_parameters: dict[str, dict],
) -> None:
    specialists = SpecialistService()
    skill_service = SkillService()

    existing = specialists.get_by_slug(db, bot.slug)
    if existing is None:
        created = specialists.create(db, bot)
        if created is None:
            logger.warning("Could not create %s; slug may already exist", bot.slug)
            return
        logger.info("Bootstrapped specialist %s under master bot", bot.slug)
    else:
        specialists.update(
            db,
            bot.slug,
            SpecialistUpdate(system_prompt=bot.system_prompt, description=bot.description),
        )
        logger.info("Refreshed %s profile", bot.slug)

    for skill_payload in skills:
        if skill_service.get_skill(db, skill_payload.slug) is None:
            created_skill = skill_service.create_skill(db, skill_payload)
            if created_skill:
                logger.info("Bootstrapped skill %s", skill_payload.slug)

    specialist_row = db.scalar(select(Specialist).where(Specialist.slug == bot.slug))
    if specialist_row is None:
        return

    for skill_payload in skills:
        skill_row = db.scalar(select(Skill).where(Skill.slug == skill_payload.slug))
        if skill_row is None:
            continue

        assignment = db.scalar(
            select(SkillAssignment).where(
                SkillAssignment.skill_id == skill_row.id,
                SkillAssignment.specialist_id == specialist_row.id,
            )
        )
        if assignment is None:
            learned = skill_service.learn_skill(
                db,
                specialist_slug=bot.slug,
                payload=SkillLearnRequest(
                    skill_slug=skill_payload.slug,
                    parameters=skill_parameters.get(skill_payload.slug, {}),
                ),
            )
            if learned is None:
                logger.warning("Could not train %s with skill %s", bot.slug, skill_payload.slug)
                continue
            assignment = db.scalar(
                select(SkillAssignment).where(SkillAssignment.id == learned.id)
            )

        if assignment and assignment.status != "active":
            skill_service.activate_skill(db, assignment.id)
            logger.info("Activated skill %s for %s", skill_payload.slug, bot.slug)
