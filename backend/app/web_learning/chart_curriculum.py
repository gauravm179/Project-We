"""Local chart-reading curriculum: skills on disk + SQLite for web-learner-bot."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR
from app.db.models import Skill, SkillAssignment, Specialist
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.skills.service import SkillService

logger = logging.getLogger(__name__)

CURRICULUM_DIR = DATA_DIR / "chart_curriculum"
WEB_LEARNER_SLUG = "web-learner-bot"

# Each entry becomes a Skill row + a JSON file under data/chart_curriculum/.
CHART_LESSONS: tuple[dict[str, str], ...] = (
    {
        "slug": "read-line-charts",
        "name": "Read Line Charts",
        "summary": "Single price series (usually close) over time.",
        "instructions": (
            "Teach line charts: one line connects closing (or chosen) prices over time. "
            "Best for seeing overall trend with less noise. "
            "Rising line = uptrend, falling = downtrend, flat = range. "
            "Compare slope and breaks of prior highs/lows."
        ),
    },
    {
        "slug": "read-bar-charts",
        "name": "Read Bar Charts",
        "summary": "OHLC bars: open/close ticks on a high-low vertical.",
        "instructions": (
            "Teach OHLC bar charts: vertical line = high to low; left tick = open; right tick = close. "
            "Close above open is typically bullish for that period; close below open bearish. "
            "Bars show the same four prices as candles without a filled body."
        ),
    },
    {
        "slug": "read-candlestick-charts",
        "name": "Read Candlestick Charts",
        "summary": "Candles: body = open↔close, wicks = high/low.",
        "instructions": (
            "Teach candlesticks: body = open to close; upper/lower wicks = high/low extremes. "
            "Green/white usually close > open; red/black usually close < open. "
            "Long body = strong period move; long wick = rejection of that extreme. "
            "Common patterns (doji, hammer, engulfing) are context tools, not guarantees."
        ),
    },
    {
        "slug": "read-heikin-ashi-charts",
        "name": "Read Heikin-Ashi Charts",
        "summary": "Smoothed candles that filter noise.",
        "instructions": (
            "Teach Heikin-Ashi: averaged/smoothed candles that filter noise vs raw OHLC. "
            "Runs of hollow/green candles often show sustained up moves; filled/red sustained down. "
            "Do not use HA open/close as exact tradeable prices — confirm on regular candles."
        ),
    },
    {
        "slug": "read-area-baseline-charts",
        "name": "Read Area and Baseline Charts",
        "summary": "Filled area / baseline views of price vs a reference.",
        "instructions": (
            "Teach area and baseline charts: area fills under a line for emphasis; "
            "baseline (e.g. Renko-like or session baseline views) highlights distance from a reference. "
            "Use them for trend clarity; still check OHLC for exact levels."
        ),
    },
    {
        "slug": "read-volume-profile-basics",
        "name": "Read Volume With Price",
        "summary": "Volume confirms or questions a price move.",
        "instructions": (
            "Teach volume with price: rising volume with a trend often confirms participation; "
            "a big move on weak volume can be fragile. "
            "Volume spikes at breaks of support/resistance deserve extra attention."
        ),
    },
    {
        "slug": "read-trend-structure",
        "name": "Read Trend Structure",
        "summary": "HH/HL vs LH/LL structure across any chart type.",
        "instructions": (
            "Teach trend structure on any chart type: higher highs + higher lows = uptrend; "
            "lower highs + lower lows = downtrend; overlapping swings = range. "
            "Mark swing points left→right before adding indicators."
        ),
    },
    {
        "slug": "read-support-resistance",
        "name": "Read Support and Resistance",
        "summary": "Price zones where moves often pause or reverse.",
        "instructions": (
            "Teach support/resistance: horizontal or diagonal zones where price repeatedly stalls. "
            "Prior highs/lows, round numbers, and dense prior trading often matter. "
            "A broken support can become resistance (and the reverse)."
        ),
    },
)


@dataclass
class CurriculumInstallResult:
    skills_installed: list[str]
    skills_refreshed: list[str]
    disk_path: str
    specialist: str
    lesson_count: int


def chart_curriculum_skills() -> tuple[SkillCreate, ...]:
    return tuple(
        SkillCreate(
            slug=item["slug"],
            name=item["name"],
            category="chart-reading",
            description=item["summary"],
            instructions=item["instructions"],
            parameters_schema={"source": {"type": "string", "default": "local-curriculum"}},
        )
        for item in CHART_LESSONS
    )


def write_curriculum_to_disk() -> Path:
    """Persist full curriculum as JSON files on the laptop under data/chart_curriculum/."""
    CURRICULUM_DIR.mkdir(parents=True, exist_ok=True)
    written_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "name": "chart-reading-curriculum",
        "version": "1",
        "written_at": written_at,
        "storage": str(CURRICULUM_DIR),
        "skills": [],
    }
    for item in CHART_LESSONS:
        payload = {
            **item,
            "category": "chart-reading",
            "written_at": written_at,
            "local_only": True,
        }
        path = CURRICULUM_DIR / f"{item['slug']}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        manifest["skills"].append(
            {"slug": item["slug"], "name": item["name"], "file": path.name}
        )
    manifest_path = CURRICULUM_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return CURRICULUM_DIR


def install_chart_curriculum(db: Session) -> CurriculumInstallResult:
    """Create/refresh chart skills in SQLite, assign to web-learner, write JSON to disk."""
    disk = write_curriculum_to_disk()
    skill_service = SkillService()
    installed: list[str] = []
    refreshed: list[str] = []

    specialist = db.scalar(select(Specialist).where(Specialist.slug == WEB_LEARNER_SLUG))
    if specialist is None:
        # Bootstrap may not have run yet in some tests — create minimal row via train path.
        from app.bootstrap import WEB_LEARNER_BOT, WEB_LEARNER_SKILL_PARAMETERS, WEB_LEARNER_SKILLS
        from app.bootstrap_common import train_specialist

        train_specialist(db, WEB_LEARNER_BOT, WEB_LEARNER_SKILLS, WEB_LEARNER_SKILL_PARAMETERS)
        specialist = db.scalar(select(Specialist).where(Specialist.slug == WEB_LEARNER_SLUG))

    for payload in chart_curriculum_skills():
        row = db.scalar(select(Skill).where(Skill.slug == payload.slug))
        if row is None:
            created = skill_service.create_skill(db, payload)
            if created:
                installed.append(payload.slug)
            row = db.scalar(select(Skill).where(Skill.slug == payload.slug))
        else:
            row.name = payload.name
            row.category = payload.category
            row.description = payload.description
            row.instructions = payload.instructions
            row.parameters_schema = json.dumps(payload.parameters_schema)
            db.commit()
            refreshed.append(payload.slug)

        if specialist is None or row is None:
            continue

        assignment = db.scalar(
            select(SkillAssignment).where(
                SkillAssignment.skill_id == row.id,
                SkillAssignment.specialist_id == specialist.id,
            )
        )
        if assignment is None:
            learned = skill_service.learn_skill(
                db,
                specialist_slug=WEB_LEARNER_SLUG,
                payload=SkillLearnRequest(
                    skill_slug=payload.slug,
                    parameters={"source": "local-curriculum"},
                ),
            )
            if learned:
                skill_service.activate_skill(db, learned.id)
        elif assignment.status != "active":
            skill_service.activate_skill(db, assignment.id)

    logger.info(
        "Chart curriculum ready: installed=%s refreshed=%s disk=%s",
        installed,
        refreshed,
        disk,
    )
    return CurriculumInstallResult(
        skills_installed=installed,
        skills_refreshed=refreshed,
        disk_path=str(disk),
        specialist=WEB_LEARNER_SLUG,
        lesson_count=len(CHART_LESSONS),
    )


def format_install_reply(result: CurriculumInstallResult) -> str:
    names = [item["name"] for item in CHART_LESSONS]
    lines = [
        "Installed a local chart-reading curriculum on this laptop for web-learner-bot.",
        f"Skills live in SQLite and as JSON files under: {result.disk_path}",
        f"Specialist: {result.specialist} · {result.lesson_count} chart skills active.",
        "",
        "Chart types covered:",
    ]
    for i, name in enumerate(names, start=1):
        lines.append(f"{i}. {name}")
    lines.extend(
        [
            "",
            "Also kept: web-search, read-web-page, compress-store-learning "
            "(tutorial pages you approve go under data/web_learning/).",
            "Ask next: “teach me candlesticks” or “explain Heikin-Ashi vs candles” "
            "(or approve internet to capture a tutorial page).",
            "I still cannot read TradingView’s live JS chart canvas as HTML — "
            "teaching uses these local skills + any stored captures.",
        ]
    )
    if result.skills_installed:
        lines.append("Newly created: " + ", ".join(result.skills_installed))
    if result.skills_refreshed and not result.skills_installed:
        lines.append("Refreshed existing curriculum skills on disk + database.")
    return "\n".join(lines)


def multi_chart_lesson(user_message: str = "") -> str:
    """Teach several chart types from the local curriculum (no web/Ollama)."""
    plain = [
        f"{i}. {item['name']}: "
        + item["instructions"].split(". ")[0].rstrip(".")
        + "."
        for i, item in enumerate(CHART_LESSONS, start=1)
    ]
    return (
        "I used the local chart-reading curriculum (stored on this laptop for web-learner-bot).\n\n"
        "How to read common chart types:\n"
        + "\n".join(plain)
        + "\n\nAsk for one type in depth (e.g. candlesticks or Heikin-Ashi), "
        "or say you want the curriculum installed/refreshed if skills are missing.\n"
        "TradingView’s live JS canvas is not readable as HTML — these skills teach chart reading locally.\n\n"
        f"Your ask: {(user_message or '').strip()[:240]}"
    )
