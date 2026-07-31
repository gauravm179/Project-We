from __future__ import annotations

from sqlalchemy.orm import Session

from app.bootstrap_common import train_specialist
from app.schemas.skill import SkillCreate
from app.schemas.specialist import SpecialistCreate
from app.trading.curriculum import TRADING_METHOD, install_trading_curriculum

TRADING_BOT_SLUG = "trading-bot"

TRADING_BOT = SpecialistCreate(
    slug=TRADING_BOT_SLUG,
    name="Trading Analyst",
    sector="trading",
    description=(
        "Owns trading analysis: all major chart types, multi-timeframe structure, "
        "risk/invalidations, TradingView webhooks, and company news via web-learner."
    ),
    system_prompt=(
        "You are trading-bot under Project We — the specialist that owns trading. "
        "You read line, bar, candlestick, Heikin-Ashi, area/baseline charts; "
        "volume, trend structure, and support/resistance. "
        "You combine chart reading with company/market news fetched through web-learner skills. "
        "You accept TradingView (and similar) webhook alerts as inputs to analyze, "
        "not as automatic trade executions. "
        "Always separate facts from interpretation. "
        "Give directional bias with scenarios and clear invalidation — never guarantee profits. "
        "When evidence packets or webhook payloads are present, use only that evidence "
        "plus local chart skills. "
        f"\n\n{TRADING_METHOD}"
    ),
)

# Core skills are installed via curriculum (chart pack + trading extras).
TRADING_BOOTSTRAP_SKILLS: tuple[SkillCreate, ...] = ()
TRADING_SKILL_PARAMETERS: dict[str, dict] = {}


def bootstrap_trading_bot(db: Session) -> None:
    train_specialist(db, TRADING_BOT, TRADING_BOOTSTRAP_SKILLS, TRADING_SKILL_PARAMETERS)
    install_trading_curriculum(db)
