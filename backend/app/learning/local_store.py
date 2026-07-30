"""Shared local learning store for master + all specialist bots."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR
from app.db.models import BotLearning, Specialist
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.skills.service import SkillService

logger = logging.getLogger(__name__)

LEARNINGS_DIR = DATA_DIR / "bot_learnings"

_POLICY_ASK = re.compile(
    r"\b("
    r"all\s+bots?|every\s+bot|each\s+bot|shared\s+learning|"
    r"bots?\s+to\s+learn|learn(?:ings?)?\s+.*\bstor|"
    r"store\s+(?:them|learnings?|new\s+learnings?)\s+local|"
    r"refer\s+(?:to\s+)?(?:them\s+)?next|next\s+time"
    r")\b",
    re.IGNORECASE,
)
_ALL_BOTS = re.compile(r"\b(all|every|each)\s+bots?\b|\bbots?\b.*\blocal", re.IGNORECASE)
_STORE_LOCAL = re.compile(
    r"\b(store|save|keep|remember).{0,40}\b(local|laptop|disk|next\s+time|refer)\b"
    r"|\b(local|laptop).{0,40}\b(store|save|learn)",
    re.IGNORECASE,
)
_EXPLICIT_LEARN = re.compile(
    r"\b(?:"
    r"remember(?:\s+that|\s+this)?|"
    r"store(?:\s+this)?(?:\s+learning)?|"
    r"save(?:\s+this)?(?:\s+learning)?|"
    r"note(?:\s+that|\s+this)?|"
    r"learn(?:\s+that|\s+this)?"
    r")\s*[:\-]?\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

SHARED_LEARNING_SKILLS: tuple[SkillCreate, ...] = (
    SkillCreate(
        slug="store-local-learning",
        name="Store Local Learning",
        category="local-learning",
        description="Save new insights on the laptop for later recall by any bot.",
        instructions=(
            "When the user teaches something useful, or a web/coding result should be kept, "
            "store a short title+content note in the shared local learning store "
            "(SQLite bot_learnings + data/bot_learnings/). Mark shared=true so all bots can reuse it."
        ),
        parameters_schema={"shared": {"type": "boolean", "default": True}},
    ),
    SkillCreate(
        slug="recall-local-learning",
        name="Recall Local Learning",
        category="local-learning",
        description="Inject prior local learnings into answers.",
        instructions=(
            "Before answering, use STORED LOCAL LEARNINGS context. Prefer corrections and "
            "prior notes over inventing conflicting advice. Cite learning IDs when relevant."
        ),
        parameters_schema={"lookback": {"type": "integer", "default": 8}},
    ),
)


@dataclass
class LearningRecord:
    id: int
    bot_slug: str
    kind: str
    title: str
    content: str
    source_ref: str | None
    shared: bool
    storage_path: str
    created_at: datetime


@dataclass
class EnableResult:
    bots: list[str]
    skills: list[str]
    learning_id: int | None
    disk_path: str
    count: int


def is_shared_learning_policy_ask(message: str) -> bool:
    """True when user wants all bots to store/reuse learnings locally."""
    text = (message or "").strip()
    if not text:
        return False
    # Must look like a policy/setup ask, not a random "learn charts" teach request.
    if not (_ALL_BOTS.search(text) or "shared learning" in text.lower()):
        # Also accept "store learnings locally so they can refer next time"
        if not (
            re.search(r"\blearnings?\b", text, re.IGNORECASE)
            and _STORE_LOCAL.search(text)
        ):
            return False
    return bool(_POLICY_ASK.search(text) or _STORE_LOCAL.search(text))


def extract_explicit_learning(message: str) -> str | None:
    """Pull 'remember that X' / 'store this: X' content from a user message."""
    text = (message or "").strip()
    if not text:
        return None
    # Skip pure policy asks — handled separately.
    if is_shared_learning_policy_ask(text) and not _EXPLICIT_LEARN.search(text):
        return None
    match = _EXPLICIT_LEARN.search(text)
    if not match:
        return None
    body = match.group(1).strip(" .")
    if len(body) < 8:
        return None
    # Avoid capturing the whole policy sentence as a "learning".
    if is_shared_learning_policy_ask(text) and "all bot" in text.lower():
        return None
    return body[:2000]


class LocalLearningStore:
    def record(
        self,
        db: Session,
        *,
        bot_slug: str,
        kind: str,
        title: str,
        content: str,
        source_ref: str | None = None,
        shared: bool = True,
    ) -> LearningRecord:
        LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
        row = BotLearning(
            bot_slug=(bot_slug or "master").strip() or "master",
            kind=(kind or "insight").strip()[:32] or "insight",
            title=(title or "Learning").strip()[:256] or "Learning",
            content=(content or "").strip()[:8000],
            source_ref=(source_ref or None),
            shared=bool(shared),
            storage_path="",
        )
        db.add(row)
        db.flush()

        path = LEARNINGS_DIR / f"{row.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": row.id,
            "bot_slug": row.bot_slug,
            "kind": row.kind,
            "title": row.title,
            "content": row.content,
            "source_ref": row.source_ref,
            "shared": row.shared,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            rel = str(path.relative_to(DATA_DIR))
        except ValueError:
            rel = str(path)
        row.storage_path = rel
        db.commit()
        db.refresh(row)
        logger.info("Stored local learning #%s (%s/%s)", row.id, row.bot_slug, row.kind)
        return self._to_record(row)

    def list_learnings(
        self,
        db: Session,
        *,
        bot_slug: str | None = None,
        limit: int = 50,
    ) -> list[LearningRecord]:
        stmt = select(BotLearning).order_by(BotLearning.id.desc()).limit(limit)
        if bot_slug:
            stmt = (
                select(BotLearning)
                .where(
                    or_(
                        BotLearning.bot_slug == bot_slug,
                        BotLearning.shared.is_(True),
                    )
                )
                .order_by(BotLearning.id.desc())
                .limit(limit)
            )
        rows = list(db.scalars(stmt).all())
        rows.reverse()
        return [self._to_record(r) for r in rows]

    def recall_context(
        self,
        db: Session,
        bot_slug: str,
        *,
        limit: int = 8,
    ) -> str:
        rows = db.scalars(
            select(BotLearning)
            .where(
                or_(
                    BotLearning.bot_slug == bot_slug,
                    BotLearning.shared.is_(True),
                )
            )
            .order_by(BotLearning.id.desc())
            .limit(limit)
        ).all()
        if not rows:
            return ""
        parts: list[str] = []
        for row in reversed(list(rows)):
            scope = "shared" if row.shared else row.bot_slug
            parts.append(
                f"- #{row.id} [{scope}/{row.kind}] {row.title}: {row.content[:400]}"
            )
        return "\n".join(parts)

    def enable_for_all_bots(self, db: Session) -> EnableResult:
        """Install store/recall skills on every specialist and seed a policy learning."""
        LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
        skill_service = SkillService()
        skill_slugs: list[str] = []

        for payload in SHARED_LEARNING_SKILLS:
            existing = skill_service.get_skill(db, payload.slug)
            if existing is None:
                skill_service.create_skill(db, payload)
            else:
                from app.db.models import Skill

                row = db.scalar(select(Skill).where(Skill.slug == payload.slug))
                if row:
                    row.name = payload.name
                    row.category = payload.category
                    row.description = payload.description
                    row.instructions = payload.instructions
                    row.parameters_schema = json.dumps(payload.parameters_schema)
                    db.commit()
            skill_slugs.append(payload.slug)

        specialists = list(db.scalars(select(Specialist).order_by(Specialist.id)).all())
        bot_slugs = [s.slug for s in specialists]

        # Assign skills to every specialist + global (master) assignment.
        targets: list[str | None] = [None, *bot_slugs]
        for slug in targets:
            for skill_slug in skill_slugs:
                from app.db.models import Skill, SkillAssignment

                skill = db.scalar(select(Skill).where(Skill.slug == skill_slug))
                if skill is None:
                    continue
                if slug is None:
                    assignment = db.scalar(
                        select(SkillAssignment).where(
                            SkillAssignment.skill_id == skill.id,
                            SkillAssignment.specialist_id.is_(None),
                        )
                    )
                else:
                    specialist = db.scalar(select(Specialist).where(Specialist.slug == slug))
                    if specialist is None:
                        continue
                    assignment = db.scalar(
                        select(SkillAssignment).where(
                            SkillAssignment.skill_id == skill.id,
                            SkillAssignment.specialist_id == specialist.id,
                        )
                    )
                if assignment is None:
                    learned = skill_service.learn_skill(
                        db,
                        specialist_slug=slug,
                        payload=SkillLearnRequest(
                            skill_slug=skill_slug,
                            parameters={"shared": True, "lookback": 8},
                        ),
                    )
                    if learned:
                        skill_service.activate_skill(db, learned.id)
                elif assignment.status != "active":
                    skill_service.activate_skill(db, assignment.id)

        # Seed a single policy note (idempotent across restarts).
        existing_policy = db.scalar(
            select(BotLearning).where(BotLearning.kind == "policy").limit(1)
        )
        learning_id = existing_policy.id if existing_policy else None
        if existing_policy is None:
            policy = self.record(
                db,
                bot_slug="master",
                kind="policy",
                title="Shared local learning enabled",
                content=(
                    "All bots (master, coding-bot, web-learner-bot, and future specialists) "
                    "store new learnings on this laptop under data/bot_learnings/ and SQLite "
                    "bot_learnings, then recall them on later asks. Say "
                    "'remember that …' to save a note; web captures and coding mistake feedback "
                    "also write shared learnings."
                ),
                source_ref="enable_for_all_bots",
                shared=True,
            )
            learning_id = policy.id

        return EnableResult(
            bots=["master", *bot_slugs],
            skills=skill_slugs,
            learning_id=learning_id,
            disk_path=str(LEARNINGS_DIR),
            count=len(self.list_learnings(db, limit=1000)),
        )

    def format_enable_reply(self, result: EnableResult) -> str:
        return "\n".join(
            [
                "Shared local learning is on for all bots on this laptop.",
                f"Storage: SQLite table bot_learnings + files under {result.disk_path}",
                f"Bots covered: {', '.join(result.bots)}",
                f"Skills active: {', '.join(result.skills)}",
                "",
                "How it works:",
                "1. New web captures/searches and coding mistake feedback are saved as shared notes.",
                "2. Say “remember that …” / “store this learning: …” to save a note yourself.",
                "3. Next time any bot answers, it gets STORED LOCAL LEARNINGS injected automatically.",
                "",
                "Try: remember that I trade on the 1-hour timeframe",
                "Then ask any bot later and it should refer back to that note.",
            ]
        )

    def _to_record(self, row: BotLearning) -> LearningRecord:
        return LearningRecord(
            id=row.id,
            bot_slug=row.bot_slug,
            kind=row.kind,
            title=row.title,
            content=row.content,
            source_ref=row.source_ref,
            shared=row.shared,
            storage_path=row.storage_path,
            created_at=row.created_at,
        )


def maybe_record_web_assist(
    db: Session,
    *,
    bot_slug: str,
    user_message: str,
    context: str,
    capture_ids: list[int] | None = None,
) -> LearningRecord | None:
    """Persist a short shared note from a successful web assist."""
    text = (context or "").strip()
    if not text or len(text) < 40:
        return None
    store = LocalLearningStore()
    title = f"Web learning from: {(user_message or '')[:80]}"
    snippet = text[:1500]
    ref = None
    if capture_ids:
        ref = "captures:" + ",".join(str(c) for c in capture_ids[:8])
    return store.record(
        db,
        bot_slug=bot_slug,
        kind="web",
        title=title,
        content=snippet,
        source_ref=ref,
        shared=True,
    )
