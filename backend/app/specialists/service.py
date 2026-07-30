from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.core.config import get_settings
from app.db.models import Specialist, SpecialistMessage
from app.learning.guidelines import GuidelinesService
from app.learning.local_store import (
    LocalLearningStore,
    extract_explicit_learning,
    is_shared_learning_policy_ask,
    maybe_record_web_assist,
)
from app.learning.service import LearningService
from app.web_learning.intent import (
    is_chart_curriculum_ask,
    is_chart_learn_ask,
    is_learn_intent,
    message_needs_web_assist,
)
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
        self._local_learnings = LocalLearningStore()
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

        if is_shared_learning_policy_ask(user_message):
            result = self._local_learnings.enable_for_all_bots(db)
            assistant_text = self._local_learnings.format_enable_reply(result)
            db.add(
                SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
            )
            db.commit()
            return SpecialistChatReply(
                specialist_slug=row.slug,
                specialist_name=row.name,
                response=assistant_text,
            )

        explicit = extract_explicit_learning(user_message)
        if explicit:
            self._local_learnings.record(
                db,
                bot_slug=slug,
                kind="insight",
                title="User note",
                content=explicit,
                source_ref="explicit-remember",
                shared=True,
            )

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

        # Chart curriculum install: multi-type skills on disk + SQLite (no web).
        if slug == "web-learner-bot" and is_chart_curriculum_ask(user_message):
            from app.progress import progress
            from app.web_learning.chart_curriculum import format_install_reply, install_chart_curriculum

            progress.step("chart-curriculum", "Installing local multi-chart skills")
            result = install_chart_curriculum(db)
            assistant_text = format_install_reply(result)
            self._local_learnings.record(
                db,
                bot_slug=slug,
                kind="curriculum",
                title="Chart curriculum installed",
                content=assistant_text[:2000],
                source_ref="chart-curriculum",
                shared=True,
            )
            db.add(
                SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
            )
            db.commit()
            return SpecialistChatReply(
                specialist_slug=row.slug,
                specialist_name=row.name,
                response=assistant_text,
            )

        # Chart/TradingView teaching: answer from local skill pack immediately.
        # Live DuckDuckGo/TradingView fetches were hanging ~100s+ and dying with HTTP 500 on Mac.
        if slug == "web-learner-bot" and is_chart_learn_ask(user_message):
            from app.progress import progress

            progress.step("fast-teach", "Local chart skill lesson (no long web wait)")
            web_assist: WebAssistResult | dict[str, object] | None = None
            if internet_approved:
                progress.step("web-assist", "Quick optional search (12s max)")
                try:
                    web_assist = await asyncio.wait_for(
                        self._web_learning.assist_for_message(
                            db,
                            user_message,
                            requesting_bot=slug,
                            auto_capture_urls=False,
                        ),
                        timeout=12.0,
                    )
                except asyncio.TimeoutError:
                    progress.step("web-timeout", "Search timed out — using local chart lesson")
                    web_assist = WebAssistResult(
                        context="WEB LEARNER ASSIST:\nSearch timed out after 12s"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Quick web assist failed")
                    progress.step("web-assist-error", f"{type(exc).__name__}: {exc}")
                    web_assist = WebAssistResult(
                        context=f"WEB LEARNER ASSIST:\nSearch/capture failed: {exc}"
                    )

            if isinstance(web_assist, WebAssistResult) and web_assist.requires_permission:
                # Still teach locally; permission only needed for live enrichment.
                web_assist = WebAssistResult(
                    context=(
                        "WEB LEARNER ASSIST:\n"
                        "Live web enrichment needs internet approval later. "
                        "Teaching from local chart skill now."
                    )
                )
            elif isinstance(web_assist, dict) and web_assist.get("requires_permission"):
                web_assist = WebAssistResult(
                    context=(
                        "WEB LEARNER ASSIST:\n"
                        "Live web enrichment needs internet approval later. "
                        "Teaching from local chart skill now."
                    )
                )
            elif web_assist is None:
                web_assist = WebAssistResult(
                    context=(
                        "WEB LEARNER ASSIST:\n"
                        "Using local chart-reading skill pack "
                        "(TradingView live canvas is JavaScript-only)."
                    )
                )

            if isinstance(web_assist, WebAssistResult):
                assistant_text = self._web_learning.compose_grounded_skill_reply(
                    user_message, web_assist
                )
            else:
                assistant_text = self._web_learning.compose_grounded_skill_reply(
                    user_message,
                    WebAssistResult(context="WEB LEARNER ASSIST:\nLocal chart skill pack"),
                )
            db.add(
                SpecialistMessage(specialist_id=row.id, role="assistant", content=assistant_text)
            )
            db.commit()
            progress.step("fast-teach-done", f"chars={len(assistant_text)}")
            return SpecialistChatReply(
                specialist_slug=row.slug,
                specialist_name=row.name,
                response=assistant_text,
            )

        web_assist = None
        if message_needs_web_assist(user_message) and not skip_web_assist_early:
            from app.progress import progress

            progress.step("web-assist", f"{slug} fetching search/pages")
            try:
                web_assist = await asyncio.wait_for(
                    self._web_learning.assist_for_message(
                        db,
                        user_message,
                        requesting_bot=slug,
                    ),
                    timeout=20.0,
                )
            except asyncio.TimeoutError:
                progress.step("web-timeout", "Web assist timed out after 20s")
                if slug == "web-learner-bot" and is_learn_intent(user_message):
                    fallback = self._web_learning.compose_grounded_skill_reply(
                        user_message,
                        WebAssistResult(context="WEB LEARNER ASSIST:\nSearch timed out after 20s"),
                    )
                    db.add(
                        SpecialistMessage(
                            specialist_id=row.id, role="assistant", content=fallback
                        )
                    )
                    db.commit()
                    return SpecialistChatReply(
                        specialist_slug=row.slug,
                        specialist_name=row.name,
                        response=fallback,
                    )
                web_assist = WebAssistResult(context="WEB LEARNER ASSIST:\nSearch timed out")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Web assist failed for %s", slug)
                progress.step("web-assist-error", f"{type(exc).__name__}: {exc}")
                if slug == "web-learner-bot" and is_learn_intent(user_message):
                    fallback = self._web_learning.compose_grounded_skill_reply(
                        user_message,
                        WebAssistResult(
                            context=(
                                "WEB LEARNER ASSIST:\n"
                                f"Search/capture failed: {type(exc).__name__}: {exc}"
                            )
                        ),
                    )
                    db.add(
                        SpecialistMessage(
                            specialist_id=row.id, role="assistant", content=fallback
                        )
                    )
                    db.commit()
                    return SpecialistChatReply(
                        specialist_slug=row.slug,
                        specialist_name=row.name,
                        response=fallback,
                    )
                web_assist = WebAssistResult(
                    context=f"WEB LEARNER ASSIST:\nSearch/capture failed: {exc}"
                )
            if isinstance(web_assist, WebAssistResult) and web_assist.requires_permission:
                assistant_text = str(
                    web_assist.message
                    or "Internet permission required for web search or page reading."
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
        stored = self._local_learnings.recall_context(db, slug, limit=8)
        if stored:
            memory_context = (
                f"{memory_context}\n\n--- STORED LOCAL LEARNINGS ---\n{stored}"
                if memory_context
                else f"--- STORED LOCAL LEARNINGS ---\n{stored}"
            )

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
            maybe_record_web_assist(
                db,
                bot_slug=slug,
                user_message=user_message,
                context=web_assist.context,
                capture_ids=list(web_assist.capture_ids or []),
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

        # Prefer grounded skill output over small-model hallucinated "open your browser" tutorials.
        if (
            slug == "web-learner-bot"
            and isinstance(web_assist, WebAssistResult)
            and web_assist.context
        ):
            from app.web_learning.intent import is_learn_intent, is_news_ask

            grounded = self._web_learning.compose_grounded_skill_reply(user_message, web_assist)
            if is_learn_intent(user_message) or is_news_ask(user_message):
                # News/learn asks stay evidence-based; skip Ollama so offline models don't block.
                from app.progress import progress

                progress.step("teach-from-web", "Building grounded skill reply (no Ollama)")
                assistant_text = grounded
            else:
                polish_prompt = (
                    full_prompt
                    + "\n\nCRITICAL RULES:\n"
                    "- You already ran web skills. Summarize ONLY from the evidence packet.\n"
                    "- NEVER say ‘open your browser’, ‘navigate to’, or invent UI click steps.\n"
                    "- Cite search numbers and capture IDs from the packet.\n"
                )
                user_for_model = (
                    f"User question:\n{user_message}\n\n"
                    f"Evidence packet from web-learner skills:\n{web_assist.context}\n\n"
                    f"Grounded draft (keep these facts):\n{grounded}\n\n"
                    "Rewrite into a clear answer. Keep capture/search citations."
                )
                try:
                    polished = await provider.generate(
                        user_for_model,
                        memory_context=memory_context,
                        system_prompt=polish_prompt,
                        specialist_slug=slug,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Web-learner polish failed, using grounded reply: %s", exc)
                    polished = ""

                bad_markers = (
                    "open your browser",
                    "navigate to the following url",
                    "step 1: visit",
                    "once you're on the page",
                    "echo mode",
                )
                polished_l = (polished or "").lower()
                if not polished.strip() or any(m in polished_l for m in bad_markers):
                    assistant_text = grounded
                else:
                    assistant_text = polished
        else:
            assistant_text = await provider.generate(
                user_message,
                memory_context=memory_context,
                system_prompt=full_prompt,
                specialist_slug=slug,
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
