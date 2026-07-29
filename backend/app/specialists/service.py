from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.core.config import get_settings
from app.db.models import Specialist, SpecialistMessage
from app.learning.guidelines import GuidelinesService
from app.learning.service import LearningService
from app.web_learning.intent import message_needs_web_assist
from app.web_learning.service import WebAssistResult, WebLearningService
from app.memory.service import MemoryService
from app.policy.service import PolicyService
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
        self._learning = LearningService()
        self._guidelines = GuidelinesService()
        self._policy = PolicyService()
        self._web_learning = WebLearningService()

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
        self, db: Session, slug: str, user_message: str
    ) -> SpecialistChatReply | None:
        row = db.scalar(select(Specialist).where(Specialist.slug == slug))
        if not row or not row.enabled:
            return None

        db.add(SpecialistMessage(specialist_id=row.id, role="user", content=user_message))
        db.flush()

        self._memory.extract_and_store(db=db, message=user_message)

        settings = get_settings()
        needs_guidelines = (
            slug == "coding-bot"
            and self._learning.message_looks_stuck_or_needs_guidelines(user_message)
        )
        wants_live_docs = (
            slug == "coding-bot"
            and self._learning.message_requests_live_internet(user_message)
        )
        internet_approved = self._policy.has_approved_capability(db, "internet")
        skip_web_assist_early = slug == "coding-bot" and (needs_guidelines or wants_live_docs)

        web_assist: WebAssistResult | dict[str, object] | None = None
        if message_needs_web_assist(user_message) and not skip_web_assist_early:
            web_assist = await self._web_learning.assist_for_message(
                db,
                user_message,
                requesting_bot=slug,
            )
            if isinstance(web_assist, WebAssistResult) and web_assist.requires_permission:
                assistant_text = str(
                    web_assist.message or "Internet permission required for web search or page reading."
                )
                db.add(
                    SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
                )
                db.commit()
                return SpecialistChatReply(
                    specialist_slug=row.slug,
                    specialist_name=row.name,
                    response=assistant_text,
                    requires_permission=True,
                    required_capability="internet",
                    permission_request_id=int(web_assist.permission_request_id),  # type: ignore[arg-type]
                )
            if isinstance(web_assist, dict) and web_assist.get("requires_permission"):
                assistant_text = str(web_assist.get("message", "Internet permission required."))
                db.add(
                    SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
                )
                db.commit()
                return SpecialistChatReply(
                    specialist_slug=row.slug,
                    specialist_name=row.name,
                    response=assistant_text,
                    requires_permission=True,
                    required_capability="internet",
                    permission_request_id=int(web_assist["permission_request_id"]),  # type: ignore[arg-type]
                )

        if (
            wants_live_docs
            and not internet_approved
            and settings.strict_local_mode
            and settings.internet_mode == "ask"
        ):
            request = self._policy.create_permission_request(
                db=db,
                capability="internet",
                reason=f"Coding bot needs live internet guidelines for: {user_message}",
            )
            matches = self._guidelines.local_match(user_message)
            local_lines = "\n".join(
                f"- {m.title}: {m.summary} ({m.url})" for m in matches
            )
            assistant_text = (
                "I can use curated local guidelines now. "
                "To fetch live official docs from the internet, please approve internet access, "
                "then ask again.\n\n"
                f"Local guidelines:\n{local_lines}"
            )
            db.add(
                SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
            )
            db.commit()
            return SpecialistChatReply(
                specialist_slug=row.slug,
                specialist_name=row.name,
                response=assistant_text,
                requires_permission=True,
                required_capability="internet",
                permission_request_id=request.id,
                used_guidelines=True,
            )

        provider = build_provider(settings)
        memory_context = self._memory.recent_context(db=db)

        if (
            web_assist
            and isinstance(web_assist, WebAssistResult)
            and web_assist.context
        ):
            memory_context = (
                f"{memory_context}\n\n--- WEB LEARNER ASSIST ---\n{web_assist.context}"
                if memory_context
                else f"--- WEB LEARNER ASSIST ---\n{web_assist.context}"
            )

        lesson_context = self._learning.build_lesson_context(db, specialist_id=row.id)
        used_lessons = bool(lesson_context)
        if lesson_context:
            memory_context = (
                f"{memory_context}\n\n--- LESSONS FROM PAST MISTAKES ---\n{lesson_context}"
                if memory_context
                else f"--- LESSONS FROM PAST MISTAKES ---\n{lesson_context}"
            )

        skill_context = self._skills.build_skill_context(db, specialist_id=row.id)
        full_prompt = row.system_prompt
        if skill_context:
            full_prompt += "\n\n--- LEARNED SKILLS ---\n" + skill_context

        used_guidelines = False
        allow_live_fetch = settings.internet_mode == "always" or (
            wants_live_docs and internet_approved
        )
        if needs_guidelines or allow_live_fetch:
            matches = self._guidelines.local_match(user_message)
            guideline_parts: list[str] = []
            for match in matches:
                snippet = match.summary
                if allow_live_fetch:
                    online = await self._guidelines.fetch_online_summary(match.url)
                    if online:
                        snippet = f"{match.summary} Online excerpt: {online}"
                guideline_parts.append(
                    f"- {match.title} ({match.language})\n  URL: {match.url}\n  Notes: {snippet}"
                )
            if guideline_parts:
                used_guidelines = True
                full_prompt += "\n\n--- CODING GUIDELINES ---\n" + "\n".join(guideline_parts)

        if lesson_context:
            full_prompt += (
                "\n\nAlways prefer the LESSONS FROM PAST MISTAKES corrections over repeating "
                "the same wrong advice."
            )

        if slug == "web-learner-bot":
            stored = self._web_learning.build_learning_context(db, specialist_id=row.id)
            if stored:
                full_prompt += "\n\n--- STORED WEB LEARNING ---\n" + stored

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
            used_lessons=used_lessons,
            used_guidelines=used_guidelines,
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
