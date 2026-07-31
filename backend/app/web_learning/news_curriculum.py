"""Local current-affairs thinking curriculum for web-learner-bot.

Trains the bot to fetch → think → analyze → ask better questions,
and stores that method as skills + a shared local learning note.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR
from app.db.models import Skill, Specialist
from app.learning.local_store import LocalLearningStore
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.skills.service import SkillService

logger = logging.getLogger(__name__)

NEWS_DIR = DATA_DIR / "news_curriculum"
WEB_LEARNER_SLUG = "web-learner-bot"

# How the bot should think when handling news (stored + used in replies).
NEWS_THINKING_METHOD = """
CURRENT-AFFAIRS THINKING METHOD (always follow)

1) FETCH (evidence first)
   - Pull live headlines/snippets from trusted feeds or search.
   - Never invent events. If evidence is thin, say so.
   - Prefer article headlines over news-portal homepages.

2) SEPARATE (facts vs interpretation)
   - Fact = what the source states (who / what / where / when).
   - Interpretation = why it might matter (clearly labeled as analysis).
   - Do not mix rumors into facts.

3) CLUSTER (see the bigger picture)
   - Group headlines into themes: geopolitics/conflict, economy, politics/governance,
     science/tech, climate/disaster, society/culture, sport.
   - Notice patterns: escalation vs de-escalation, regional concentration, repeats.

4) ANALYZE (ask yourself before answering)
   - What changed today vs “business as usual”?
   - Who is affected (people, markets, governments)?
   - What is missing from the brief (numbers, second side, verification)?
   - What would a careful reader doubt or double-check?

5) EXPLAIN (teach, don’t dump links)
   - Lead with 4–8 headline bullets + 1-line context each.
   - Add a short “Why it matters” section using only supported themes.
   - End with 2–4 sharp follow-up questions the user can ask next.

6) MODEL ROLES (local dual-LLM)
   - Fast chat model (Qwen): keep replies short when only a hello/simple ask.
   - Reasoning model (DeepSeek): use for analysis / “why it matters” / question design
     on top of fetched evidence — never to invent news.
""".strip()

NEWS_ANALYSIS_SKILLS: tuple[SkillCreate, ...] = (
    SkillCreate(
        slug="fetch-current-affairs",
        name="Fetch Current Affairs",
        category="current-affairs",
        description="Fetch live news headlines from RSS/search as evidence.",
        instructions=(
            "For current-affairs / today's news asks: fetch live headlines (RSS preferred, "
            "search fallback). Keep only real titles + snippets + source URLs. "
            "Reject portal fluff like 'latest news and updates'."
        ),
        parameters_schema={"limit": {"type": "integer", "default": 8}},
    ),
    SkillCreate(
        slug="analyze-current-affairs",
        name="Analyze Current Affairs",
        category="current-affairs",
        description="Think through news: facts, themes, why it matters, gaps.",
        instructions=(
            NEWS_THINKING_METHOD
            + "\n\nWhen evidence is present, produce: Headlines → Themes → Why it matters → "
            "Questions to ask next. Label analysis clearly. Never invent events."
        ),
        parameters_schema={"max_headlines": {"type": "integer", "default": 8}},
    ),
    SkillCreate(
        slug="ask-news-questions",
        name="Ask News Follow-up Questions",
        category="current-affairs",
        description="Propose sharp follow-up questions after a news briefing.",
        instructions=(
            "After briefing, ask 2–4 questions that deepen understanding, e.g. causes, "
            "second-order effects, regional impact, or what to verify next. "
            "Questions must be answerable from further fetching, not speculation."
        ),
        parameters_schema={"count": {"type": "integer", "default": 3}},
    ),
)

_THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Geopolitics / conflict",
        (
            "war",
            "gaza",
            "ukraine",
            "hamas",
            "israel",
            "military",
            "missile",
            "ceasefire",
            "sanction",
            "troop",
            "conflict",
            "attack",
            "disarm",
        ),
    ),
    (
        "Migration / borders",
        ("migrant", "refugee", "border", "asylum", "deport", "ceuta", "crossing"),
    ),
    (
        "Politics / governance",
        (
            "president",
            "election",
            "parliament",
            "minister",
            "cabinet",
            "corruption",
            "jail",
            "sentence",
            "court",
            "vote",
            "policy",
        ),
    ),
    (
        "Economy / markets",
        ("market", "inflation", "bank", "trade", "tariff", "stock", "gdp", "jobs", "oil"),
    ),
    (
        "Sport",
        ("football", "fifa", "uefa", "cricket", "olympic", "match", "player", "club"),
    ),
    (
        "Science / tech",
        ("ai", "chip", "space", "nasa", "climate", "virus", "vaccine", "research"),
    ),
    (
        "Disaster / climate",
        ("storm", "flood", "earthquake", "wildfire", "hurricane", "drought", "disaster"),
    ),
)


def classify_themes(headlines: list[str]) -> list[tuple[str, list[str]]]:
    """Group headlines into analysis themes."""
    buckets: dict[str, list[str]] = {}
    for line in headlines:
        text = line.lower()
        matched = False
        for theme, keys in _THEME_RULES:
            if any(k in text for k in keys):
                buckets.setdefault(theme, []).append(line)
                matched = True
                break
        if not matched:
            buckets.setdefault("World / other", []).append(line)
    return [(theme, items) for theme, items in buckets.items() if items]


def why_it_matters(themes: list[tuple[str, list[str]]]) -> list[str]:
    """Deterministic analysis bullets from theme clusters (no invented facts)."""
    notes: list[str] = []
    theme_names = {t for t, _ in themes}
    if "Geopolitics / conflict" in theme_names:
        notes.append(
            "Conflict / diplomacy items can shift humanitarian risk and regional alliances — "
            "check whether the story is escalation, negotiation, or aftermath."
        )
    if "Migration / borders" in theme_names:
        notes.append(
            "Large migration movements usually signal pressure on borders, politics, and aid — "
            "ask for numbers, origin countries, and official response."
        )
    if "Politics / governance" in theme_names:
        notes.append(
            "Legal/political rulings matter when they change power, precedent, or public trust — "
            "separate the court outcome from partisan commentary."
        )
    if "Economy / markets" in theme_names:
        notes.append(
            "Economic headlines matter through prices, jobs, and trade — "
            "look for the concrete metric (rate, deal, jobs) before drawing conclusions."
        )
    if "Sport" in theme_names:
        notes.append(
            "Sport governance stories (FIFA/UEFA etc.) can affect tournaments and national teams — "
            "treat them as institutional politics as much as sport."
        )
    if "Disaster / climate" in theme_names:
        notes.append(
            "Disaster items need location, scale, and response — "
            "avoid over-generalizing from a single event to global climate claims."
        )
    if not notes:
        notes.append(
            "These look like mixed world updates — prioritize verified who/what/where before "
            "inferring wider impact."
        )
    return notes[:4]


def follow_up_questions(themes: list[tuple[str, list[str]]]) -> list[str]:
    """Thinking-driven questions the bot should invite next."""
    qs: list[str] = []
    theme_names = {t for t, _ in themes}
    if "Geopolitics / conflict" in theme_names:
        qs.append("What are the confirmed facts vs claims in the biggest conflict story?")
        qs.append("Who are the key actors and what changed in the last 24–48 hours?")
    if "Migration / borders" in theme_names:
        qs.append("What triggered the migration spike and how are authorities responding?")
    if "Politics / governance" in theme_names:
        qs.append("What exactly did the court/government decide, and what happens next procedurally?")
    if "Economy / markets" in theme_names:
        qs.append("Which economic number moved, and who is most affected?")
    if "Sport" in theme_names:
        qs.append("Is this a rules/governance dispute or an on-field story?")
    if not qs:
        qs.append("Which headline should I deepen with a full article read?")
        qs.append("Do you want a India-focused, US-focused, or world-only briefing next?")
    qs.append("Want me to verify one story with a second source?")
    # Dedupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:4]


def strip_bullet(text: str) -> str:
    return re.sub(r"^[•\-\d\.\)\s]+", "", text or "").strip()


def install_news_curriculum(db: Session) -> dict[str, object]:
    """Install news-thinking skills + shared local learning on disk/SQLite."""
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    method_path = NEWS_DIR / "thinking_method.json"
    method_path.write_text(
        json.dumps(
            {
                "name": "current-affairs-thinking",
                "version": "1",
                "method": NEWS_THINKING_METHOD,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    skill_service = SkillService()
    installed: list[str] = []
    refreshed: list[str] = []

    for payload in NEWS_ANALYSIS_SKILLS:
        row = db.scalar(select(Skill).where(Skill.slug == payload.slug))
        if row is None:
            created = skill_service.create_skill(db, payload)
            if created:
                installed.append(payload.slug)
        else:
            row.name = payload.name
            row.category = payload.category
            row.description = payload.description
            row.instructions = payload.instructions
            row.parameters_schema = json.dumps(payload.parameters_schema)
            refreshed.append(payload.slug)
            db.commit()

    specialist = db.scalar(select(Specialist).where(Specialist.slug == WEB_LEARNER_SLUG))
    if specialist is not None:
        from app.db.models import SkillAssignment

        for payload in NEWS_ANALYSIS_SKILLS:
            skill_row = db.scalar(select(Skill).where(Skill.slug == payload.slug))
            if skill_row is None:
                continue
            existing = db.scalar(
                select(SkillAssignment).where(
                    SkillAssignment.skill_id == skill_row.id,
                    SkillAssignment.specialist_id == specialist.id,
                )
            )
            if existing is None:
                learned = skill_service.learn_skill(
                    db,
                    specialist_slug=WEB_LEARNER_SLUG,
                    payload=SkillLearnRequest(
                        skill_slug=payload.slug,
                        parameters=(
                            {"limit": 8}
                            if payload.slug.startswith("fetch")
                            else {"count": 3}
                        ),
                    ),
                )
                if learned and learned.status != "active":
                    skill_service.activate_skill(db, learned.id)
            elif existing.status != "active":
                skill_service.activate_skill(db, existing.id)

    store = LocalLearningStore()
    learning = store.record(
        db,
        bot_slug="web-learner-bot",
        kind="method",
        title="Current-affairs thinking method",
        content=NEWS_THINKING_METHOD,
        source_ref=str(method_path.relative_to(DATA_DIR)),
        shared=True,
    )

    logger.info(
        "News curriculum ready: installed=%s refreshed=%s learning=#%s disk=%s",
        installed,
        refreshed,
        learning.id,
        NEWS_DIR,
    )
    return {
        "installed": installed,
        "refreshed": refreshed,
        "learning_id": learning.id,
        "disk_path": str(NEWS_DIR),
    }
