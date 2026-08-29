"""Trading curriculum: chart types + analysis method for trading-bot."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DATA_DIR
from app.db.models import Skill, SkillAssignment, Specialist
from app.learning.local_store import LocalLearningStore
from app.schemas.skill import SkillCreate, SkillLearnRequest
from app.skills.service import SkillService
from app.web_learning.chart_curriculum import CHART_LESSONS, chart_curriculum_skills

logger = logging.getLogger(__name__)

TRADING_DIR = DATA_DIR / "trading_curriculum"
TRADING_BOT_SLUG = "trading-bot"

TRADING_METHOD = """
TRADING ANALYSIS METHOD (always follow)

1) CHART FIRST
   - Identify chart type (line, bar, candle, Heikin-Ashi, area/baseline).
   - Mark trend structure: HH/HL vs LH/LL vs range.
   - Mark support/resistance and obvious liquidity / prior swing zones.
   - Note volume confirmation when available.

2) MULTI-TIMEFRAME (when possible)
   - Higher TF = bias (daily/4H). Lower TF = timing (1H/15m).
   - Do not fight the higher-timeframe structure without saying so.

3) COMPANY / MARKET CONTEXT (news)
   - Pull recent company or market news via web-learner skills when a ticker is known.
   - Separate FACT (reported event) from INTERPRETATION (how it may affect price).
   - Earnings, guidance, lawsuits, regulation, and macro prints matter more than random headlines.

4) WEBHOOK / ALERT CONTEXT
   - Treat TradingView (or other) webhooks as event inputs, not automatic trade orders.
   - Map alert → chart context → invalidation → risk.
   - If price/timeframe missing, state what is unknown.

5) PREDICTION DISCIPLINE (no false certainty)
   - Give a directional BIAS with confidence (low/medium/high), not a promise.
   - State entry zone, invalidation (stop idea), and targets as scenarios.
   - Always say what would prove the idea wrong.
   - Never claim guaranteed profits or “sure tips”.

6) OUTPUT FORMAT
   - Chart read
   - News/context (if fetched)
   - Bias + scenarios
   - Risks / invalidation
   - Optional follow-up questions
""".strip()

EXTRA_TRADING_LESSONS: tuple[dict[str, str], ...] = (
    {
        "slug": "multi-timeframe-bias",
        "name": "Multi-Timeframe Bias",
        "summary": "Align higher-timeframe trend with lower-timeframe entries.",
        "instructions": (
            "Teach multi-timeframe analysis: decide bias on higher TF (structure + S/R), "
            "time entries on lower TF only in the direction of that bias unless clearly "
            "calling a counter-trend scalp with tight invalidation."
        ),
    },
    {
        "slug": "risk-reward-invalidations",
        "name": "Risk, Reward, Invalidation",
        "summary": "Define invalidation before targets.",
        "instructions": (
            "Before any target, define what proves the idea wrong (structure break, "
            "level reclaim, news contradiction). Prefer asymmetric risk/reward. "
            "Position size is the user's choice — discuss risk framing, not guaranteed size."
        ),
    },
    {
        "slug": "indicator-context",
        "name": "Indicators With Context",
        "summary": "RSI/EMA/MACD support price action; they do not replace it.",
        "instructions": (
            "Use indicators as confirmation: EMA slope/stack for trend, RSI for momentum "
            "extremes in context, MACD for momentum shifts. Never treat a single indicator "
            "cross as a standalone prediction."
        ),
    },
    {
        "slug": "news-catalyst-trading",
        "name": "News Catalyst Trading",
        "summary": "Combine company news with chart levels.",
        "instructions": (
            "When a ticker is present, fetch recent company news. Map catalysts to levels: "
            "gap risk, trend continuation vs reversal, and whether the move is news-driven. "
            "Label facts vs opinion. Use web-learner search/RSS evidence only."
        ),
    },
    {
        "slug": "webhook-alert-handling",
        "name": "Webhook Alert Handling",
        "summary": "Interpret TradingView/other webhook alerts carefully.",
        "instructions": (
            "Parse webhook ticker, action, price, timeframe, and message. "
            "Treat as an alert to analyze — not auto-execution. "
            "Respond with chart-consistent bias, invalidation, and whether news agrees or conflicts."
        ),
    },
    {
        "slug": "learn-from-trading-sites",
        "name": "Learn From Trading Sites",
        "summary": "Google Zerodha/TradingView/etc, pick pages, save IMP notes.",
        "instructions": (
            "When asked to learn from the internet or sites like Zerodha Varsity / TradingView: "
            "search Google with site filters, prefer education pages over live chart widgets, "
            "capture readable HTML, distill IMP notes, and store them in local learnings "
            "for future recall. Do not invent content that was not on the page."
        ),
    },
)


def trading_skills() -> tuple[SkillCreate, ...]:
    chart_skills = chart_curriculum_skills()
    extras = tuple(
        SkillCreate(
            slug=item["slug"],
            name=item["name"],
            category="trading",
            description=item["summary"],
            instructions=item["instructions"],
            parameters_schema={"source": {"type": "string", "default": "trading-curriculum"}},
        )
        for item in EXTRA_TRADING_LESSONS
    )
    return chart_skills + extras


def write_trading_curriculum_to_disk() -> Path:
    TRADING_DIR.mkdir(parents=True, exist_ok=True)
    written_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "name": "trading-curriculum",
        "version": "1",
        "written_at": written_at,
        "method": TRADING_METHOD,
        "skills": [],
    }
    for item in list(CHART_LESSONS) + list(EXTRA_TRADING_LESSONS):
        payload = {**item, "written_at": written_at, "bot": TRADING_BOT_SLUG}
        path = TRADING_DIR / f"{item['slug']}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        manifest["skills"].append({"slug": item["slug"], "file": path.name})
    (TRADING_DIR / "thinking_method.json").write_text(
        json.dumps({"method": TRADING_METHOD, "written_at": written_at}, indent=2) + "\n",
        encoding="utf-8",
    )
    (TRADING_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return TRADING_DIR


def install_trading_curriculum(db: Session) -> dict[str, object]:
    """Install chart+trading skills on trading-bot and store method locally."""
    disk = write_trading_curriculum_to_disk()
    skill_service = SkillService()
    installed: list[str] = []
    refreshed: list[str] = []

    specialist = db.scalar(select(Specialist).where(Specialist.slug == TRADING_BOT_SLUG))
    for payload in trading_skills():
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
        existing = db.scalar(
            select(SkillAssignment).where(
                SkillAssignment.skill_id == row.id,
                SkillAssignment.specialist_id == specialist.id,
            )
        )
        if existing is None:
            learned = skill_service.learn_skill(
                db,
                specialist_slug=TRADING_BOT_SLUG,
                payload=SkillLearnRequest(
                    skill_slug=payload.slug,
                    parameters={"source": "trading-curriculum"},
                ),
            )
            if learned and learned.status != "active":
                skill_service.activate_skill(db, learned.id)
        elif existing.status != "active":
            skill_service.activate_skill(db, existing.id)

    learning = LocalLearningStore().record(
        db,
        bot_slug=TRADING_BOT_SLUG,
        kind="method",
        title="Trading analysis method",
        content=TRADING_METHOD,
        source_ref=str(disk.relative_to(DATA_DIR)),
        shared=True,
    )
    logger.info(
        "Trading curriculum ready: installed=%s refreshed=%s learning=#%s disk=%s",
        installed,
        refreshed,
        learning.id,
        disk,
    )
    return {
        "installed": installed,
        "refreshed": refreshed,
        "learning_id": learning.id,
        "disk_path": str(disk),
        "specialist": TRADING_BOT_SLUG,
    }


def build_chart_knowledge_brief() -> str:
    """Compact chart knowledge block for prompts / grounded replies."""
    lines = ["LOCAL CHART KNOWLEDGE (trading-bot):"]
    for item in CHART_LESSONS:
        lines.append(f"- {item['name']}: {item['instructions']}")
    for item in EXTRA_TRADING_LESSONS:
        lines.append(f"- {item['name']}: {item['instructions']}")
    lines.append("")
    lines.append(TRADING_METHOD)
    return "\n".join(lines)
