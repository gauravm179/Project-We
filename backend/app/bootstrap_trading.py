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
        "You actively learn from the internet: Google trusted education sites "
        "(Zerodha Varsity, TradingView support/education, Investopedia, NSE guides), "
        "choose useful pages (not live chart widgets), capture them, and save IMP notes "
        "locally for future reference on later asks. "
        "You accept TradingView (and similar) webhook alerts as inputs to analyze, "
        "not as automatic trade executions. "
        "Always separate facts from interpretation. "
        "Give directional bias with scenarios and clear invalidation — never guarantee profits. "
        "When evidence packets or webhook payloads are present, use only that evidence "
        "plus local chart skills and saved IMP notes. "
        f"\n\n{TRADING_METHOD}"
    ),
)

# Core skills are installed via curriculum (chart pack + trading extras).
TRADING_BOOTSTRAP_SKILLS: tuple[SkillCreate, ...] = ()
TRADING_SKILL_PARAMETERS: dict[str, dict] = {}


def bootstrap_trading_bot(db: Session) -> None:
    from app.schemas.specialist import SpecialistUpdate
    from app.specialists.service import SpecialistService
    from app.trading.ta_curriculum import install_ta_kb_local

    train_specialist(db, TRADING_BOT, TRADING_BOOTSTRAP_SKILLS, TRADING_SKILL_PARAMETERS)
    # Always keep trading-bot enabled after refresh.
    SpecialistService().update(
        db, TRADING_BOT_SLUG, SpecialistUpdate(enabled=True)
    )
    install_trading_curriculum(db)
    # Offline TA KB (all chart types, patterns, indicators, scenarios).
    try:
        install_ta_kb_local(db)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("TA KB bootstrap skipped: %s", exc)
