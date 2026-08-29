"""Full technical-analysis curriculum: chart types, patterns, indicators, scenarios."""

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

logger = logging.getLogger(__name__)

TA_KB_DIR = DATA_DIR / "trading_ta_kb"
TRADING_BOT_SLUG = "trading-bot"

# category: chart-type | pattern | indicator | scenario | structure
TA_TOPICS: tuple[dict[str, str], ...] = (
    # --- Chart types (TradingView + standard) ---
    {
        "slug": "ta-line-chart",
        "category": "chart-type",
        "name": "Line Chart",
        "summary": "Close (or single series) connected over time.",
        "instructions": (
            "Line chart: one price series (usually close). Best for clean trend view. "
            "Mark slope changes and prior swing highs/lows. Weak for exact OHLC timing."
        ),
        "web_query": "site:tradingview.com/support line chart how to read",
    },
    {
        "slug": "ta-bar-chart",
        "category": "chart-type",
        "name": "Bar Chart (OHLC)",
        "summary": "Vertical high-low with open/close ticks.",
        "instructions": (
            "OHLC bars: vertical line = high to low; ticks show open (left) and close (right). "
            "Same four prices as candles without filled body."
        ),
        "web_query": "site:tradingview.com/support bar chart OHLC",
    },
    {
        "slug": "ta-candlestick",
        "category": "chart-type",
        "name": "Candlestick Chart",
        "summary": "Body = open↔close, wicks = high/low.",
        "instructions": (
            "Candles: body shows open-close range; wicks show rejection at extremes. "
            "Context patterns (doji, hammer, engulfing) need trend + level — not standalone signals."
        ),
        "web_query": "site:zerodha.com/varsity candlestick patterns",
    },
    {
        "slug": "ta-heikin-ashi",
        "category": "chart-type",
        "name": "Heikin-Ashi",
        "summary": "Smoothed averaged candles for trend persistence.",
        "instructions": (
            "Heikin-Ashi smooths noise; consecutive same-color candles suggest trend persistence. "
            "Confirm entries on regular candles — HA levels are not exact trade prices."
        ),
        "web_query": "site:tradingview.com/support heikin ashi",
    },
    {
        "slug": "ta-area-baseline",
        "category": "chart-type",
        "name": "Area & Baseline",
        "summary": "Filled area or distance from a baseline reference.",
        "instructions": (
            "Area charts emphasize magnitude of move; baseline charts show deviation from a reference. "
            "Use for trend clarity; verify exact levels on OHLC."
        ),
        "web_query": "site:tradingview.com/support area chart baseline",
    },
    {
        "slug": "ta-renko",
        "category": "chart-type",
        "name": "Renko",
        "summary": "Brick chart ignoring time; moves by fixed price amount.",
        "instructions": (
            "Renko bricks form when price moves by a set amount — time is not fixed per brick. "
            "Good for filtering noise; lag on reversals. Define brick size vs instrument volatility."
        ),
        "web_query": "site:tradingview.com/support renko chart",
    },
    {
        "slug": "ta-kagi",
        "category": "chart-type",
        "name": "Kagi",
        "summary": "Thick/thin lines on direction reversals.",
        "instructions": (
            "Kagi lines thicken on up moves and thin on down (or vice versa by settings). "
            "Reversal amount is configurable. Use for trend bias, not precise entries alone."
        ),
        "web_query": "site:tradingview.com/support kagi chart",
    },
    {
        "slug": "ta-point-figure",
        "category": "chart-type",
        "name": "Point & Figure",
        "summary": "X/O columns for pure price movement.",
        "instructions": (
            "Point & Figure ignores time; X columns = rising, O = falling. "
            "Double-top/bottom style breakouts on P&F differ from time-based charts."
        ),
        "web_query": "site:investopedia.com point and figure chart",
    },
    {
        "slug": "ta-range-bars",
        "category": "chart-type",
        "name": "Range Bars",
        "summary": "New bar only after price travels a set range.",
        "instructions": (
            "Range bars close when price moves the configured range — compresses quiet periods. "
            "Each bar has equal range; volume/time per bar varies."
        ),
        "web_query": "site:tradingview.com/support range bars",
    },
    # --- Structure ---
    {
        "slug": "ta-trend-structure",
        "category": "structure",
        "name": "Trend Structure (HH/HL)",
        "summary": "Higher highs/lows vs lower highs/lows.",
        "instructions": (
            "Uptrend: HH + HL. Downtrend: LH + LL. Range: overlapping swings. "
            "Mark swings left-to-right before indicators."
        ),
        "web_query": "site:zerodha.com/varsity dow theory trend",
    },
    {
        "slug": "ta-support-resistance",
        "category": "structure",
        "name": "Support & Resistance",
        "summary": "Zones where price stalls or reverses.",
        "instructions": (
            "S/R from prior swings, gaps, round numbers, volume nodes. "
            "Broken support often becomes resistance (role reversal)."
        ),
        "web_query": "site:zerodha.com/varsity support resistance",
    },
    {
        "slug": "ta-trendlines-channels",
        "category": "structure",
        "name": "Trendlines & Channels",
        "summary": "Diagonal boundaries of a trend.",
        "instructions": (
            "Connect swing lows in uptrend (support trendline) or highs in downtrend. "
            "Parallel channel = trend + opposite boundary. Break = potential acceleration or reversal."
        ),
        "web_query": "site:tradingview.com/support trend line channel",
    },
    {
        "slug": "ta-multi-timeframe",
        "category": "structure",
        "name": "Multi-Timeframe Analysis",
        "summary": "Higher TF bias, lower TF timing.",
        "instructions": (
            "Decide bias on daily/4H; time entries on 1H/15m in bias direction. "
            "Counter-trend scalps need explicit invalidation."
        ),
        "web_query": "site:zerodha.com/varsity multiple timeframe analysis",
    },
    # --- Patterns ---
    {
        "slug": "ta-pattern-head-shoulders",
        "category": "pattern",
        "name": "Head & Shoulders",
        "summary": "Reversal: three peaks, middle highest.",
        "instructions": (
            "Head & shoulders: left shoulder, higher head, lower right shoulder, neckline break. "
            "Inverse H&S is bullish mirror. Measure target ≈ head height from neckline."
        ),
        "web_query": "site:investopedia.com head and shoulders pattern",
    },
    {
        "slug": "ta-pattern-double-top-bottom",
        "category": "pattern",
        "name": "Double Top / Double Bottom",
        "summary": "Two tests of a level then reversal.",
        "instructions": (
            "Double top: two highs near same level, break below valley = bearish. "
            "Double bottom: two lows, break above peak = bullish. Confirm with volume."
        ),
        "web_query": "site:investopedia.com double top double bottom",
    },
    {
        "slug": "ta-pattern-triangles",
        "category": "pattern",
        "name": "Triangles (Asc/Desc/Sym)",
        "summary": "Converging trendlines; breakout direction matters.",
        "instructions": (
            "Ascending triangle: flat resistance + rising lows (often bullish bias). "
            "Descending: flat support + lower highs. Symmetrical: wait for break direction."
        ),
        "web_query": "site:investopedia.com triangle chart pattern",
    },
    {
        "slug": "ta-pattern-flags-pennants",
        "category": "pattern",
        "name": "Flags & Pennants",
        "summary": "Short consolidation after a sharp move.",
        "instructions": (
            "Flag = parallel channel against prior move; pennant = small symmetrical triangle. "
            "Continuation bias on break in direction of prior impulse. Measure = flagpole length."
        ),
        "web_query": "site:investopedia.com flag pennant pattern",
    },
    {
        "slug": "ta-pattern-wedges",
        "category": "pattern",
        "name": "Rising / Falling Wedges",
        "summary": "Converging lines; often reversal at end.",
        "instructions": (
            "Rising wedge in uptrend can be bearish reversal; falling wedge in downtrend can be bullish. "
            "Context and break direction matter more than pattern label alone."
        ),
        "web_query": "site:investopedia.com wedge pattern trading",
    },
    # --- Indicators ---
    {
        "slug": "ta-ind-ema-sma",
        "category": "indicator",
        "name": "Moving Averages (EMA/SMA)",
        "summary": "Trend filter and dynamic S/R.",
        "instructions": (
            "EMA reacts faster than SMA. Stack (e.g. 20>50>200) suggests trend. "
            "Price crossing MA is context — combine with structure, not alone."
        ),
        "web_query": "site:tradingview.com/support moving average",
    },
    {
        "slug": "ta-ind-rsi",
        "category": "indicator",
        "name": "RSI",
        "summary": "Momentum oscillator 0–100.",
        "instructions": (
            "RSI >70 overbought, <30 oversold — only meaningful with trend context. "
            "Divergence (price new high, RSI not) can warn of weakening momentum."
        ),
        "web_query": "site:tradingview.com/support RSI relative strength index",
    },
    {
        "slug": "ta-ind-macd",
        "category": "indicator",
        "name": "MACD",
        "summary": "Momentum via EMA spread and signal line.",
        "instructions": (
            "MACD line vs signal cross shows momentum shift; histogram shows strength. "
            "Late in strong trends crosses can whipsaw — prefer with structure."
        ),
        "web_query": "site:tradingview.com/support MACD",
    },
    {
        "slug": "ta-ind-bollinger",
        "category": "indicator",
        "name": "Bollinger Bands",
        "summary": "Volatility bands around a moving average.",
        "instructions": (
            "Bands widen in volatility, squeeze before expansion. "
            "Touching upper band ≠ automatic sell in strong trend (riding the band)."
        ),
        "web_query": "site:tradingview.com/support bollinger bands",
    },
    {
        "slug": "ta-ind-stochastic",
        "category": "indicator",
        "name": "Stochastic",
        "summary": "Close position within recent range.",
        "instructions": (
            "%K/%D crosses in overbought/oversold zones — best in ranges or pullbacks in trend. "
            "Avoid fighting strong momentum with oscillator alone."
        ),
        "web_query": "site:tradingview.com/support stochastic oscillator",
    },
    {
        "slug": "ta-ind-adx",
        "category": "indicator",
        "name": "ADX",
        "summary": "Trend strength (not direction).",
        "instructions": (
            "ADX rising = stronger trend (direction from price/MA). "
            "Low ADX = chop/range — reduce breakout expectations."
        ),
        "web_query": "site:tradingview.com/support ADX average directional index",
    },
    {
        "slug": "ta-ind-atr",
        "category": "indicator",
        "name": "ATR",
        "summary": "Average true range for volatility sizing.",
        "instructions": (
            "ATR measures typical bar range — use for stop distance and position sizing ideas. "
            "Higher ATR = wider stops needed; not a direction signal."
        ),
        "web_query": "site:zerodha.com/varsity volatility ATR",
    },
    {
        "slug": "ta-ind-vwap",
        "category": "indicator",
        "name": "VWAP",
        "summary": "Volume-weighted average price (intraday anchor).",
        "instructions": (
            "VWAP is session volume-weighted fair value for intraday. "
            "Price above VWAP = relative strength intraday; institutional execution benchmark."
        ),
        "web_query": "site:investopedia.com VWAP trading",
    },
    {
        "slug": "ta-ind-ichimoku",
        "category": "indicator",
        "name": "Ichimoku Cloud",
        "summary": "Multi-line system: cloud, tenkan, kijun.",
        "instructions": (
            "Price above cloud = bullish bias; below = bearish. Cloud thickness = support/resistance strength. "
            "TK cross and chikou span add confirmation — learn components before trading."
        ),
        "web_query": "site:tradingview.com/support ichimoku cloud",
    },
    {
        "slug": "ta-ind-fibonacci",
        "category": "indicator",
        "name": "Fibonacci Retracement",
        "summary": "Pullback levels (38.2%, 50%, 61.8%).",
        "instructions": (
            "Draw from swing low to high (uptrend pullback) or high to low (downtrend). "
            "Common reaction zones 38.2–61.8%; confluence with structure improves odds."
        ),
        "web_query": "site:zerodha.com/varsity fibonacci retracement",
    },
    # --- Scenarios ---
    {
        "slug": "ta-scenario-breakout",
        "category": "scenario",
        "name": "Breakout Trade",
        "summary": "Trade through S/R with follow-through.",
        "instructions": (
            "Breakout needs close beyond level + volume (when available). "
            "False break = wick through and close back inside — wait for retest or skip."
        ),
        "web_query": "site:zerodha.com/varsity breakout trading",
    },
    {
        "slug": "ta-scenario-pullback",
        "category": "scenario",
        "name": "Pullback Entry",
        "summary": "Enter on retest in trend direction.",
        "instructions": (
            "In uptrend, buy pullback to support/MA/50% fib with bullish reaction. "
            "Invalidation = loss of swing low or structure break."
        ),
        "web_query": "site:zerodha.com/varsity pullback trading",
    },
    {
        "slug": "ta-scenario-range",
        "category": "scenario",
        "name": "Range Trading",
        "summary": "Buy support, sell resistance inside a box.",
        "instructions": (
            "Range: fade extremes until break. Tight stops outside range. "
            "ADX low often accompanies ranges."
        ),
        "web_query": "site:investopedia.com range bound trading",
    },
    {
        "slug": "ta-scenario-reversal",
        "category": "scenario",
        "name": "Reversal at Key Level",
        "summary": "Counter-trend only with strong evidence.",
        "instructions": (
            "Reversal needs level + pattern + momentum shift (e.g. RSI div, structure break). "
            "Higher risk than continuation — smaller size, tight invalidation."
        ),
        "web_query": "site:investopedia.com trend reversal trading",
    },
    {
        "slug": "ta-scenario-gap",
        "category": "scenario",
        "name": "Gap Trading",
        "summary": "Gap up/down, fill or continuation.",
        "instructions": (
            "Gaps from news/earnings. Partial fill common; full fill or gap-and-go depends on catalyst. "
            "Map gap edges as S/R."
        ),
        "web_query": "site:investopedia.com gap trading strategy",
    },
    {
        "slug": "ta-scenario-webhook",
        "category": "scenario",
        "name": "Webhook Alert Scenario",
        "summary": "Map TradingView alert to chart context.",
        "instructions": (
            "Webhook = event input. Check TF, level, news, and saved TA KB before bias. "
            "Never auto-trade from alert alone."
        ),
        "web_query": "site:tradingview.com/support alerts webhooks",
    },
)


def ta_skills() -> tuple[SkillCreate, ...]:
    return tuple(
        SkillCreate(
            slug=item["slug"],
            name=item["name"],
            category=f"ta-{item['category']}",
            description=item["summary"],
            instructions=item["instructions"],
            parameters_schema={"source": {"type": "string", "default": "ta-kb"}},
        )
        for item in TA_TOPICS
    )


def write_ta_kb_to_disk() -> Path:
    TA_KB_DIR.mkdir(parents=True, exist_ok=True)
    written_at = datetime.now(timezone.utc).isoformat()
    by_category: dict[str, list[str]] = {}
    for item in TA_TOPICS:
        payload = {**item, "written_at": written_at, "bot": TRADING_BOT_SLUG}
        path = TA_KB_DIR / f"{item['slug']}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        by_category.setdefault(item["category"], []).append(item["slug"])
    manifest = {
        "name": "trading-ta-kb",
        "version": "1",
        "written_at": written_at,
        "topic_count": len(TA_TOPICS),
        "categories": by_category,
    }
    (TA_KB_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return TA_KB_DIR


def install_ta_kb_local(db: Session) -> dict[str, object]:
    """Install full TA curriculum to disk, skills, and bot_learnings (offline)."""
    disk = write_ta_kb_to_disk()
    skill_service = SkillService()
    store = LocalLearningStore()
    installed: list[str] = []
    refreshed: list[str] = []
    learning_ids: list[int] = []

    specialist = db.scalar(select(Specialist).where(Specialist.slug == TRADING_BOT_SLUG))
    for payload in ta_skills():
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
                    parameters={"source": "ta-kb"},
                ),
            )
            if learned and learned.status != "active":
                skill_service.activate_skill(db, learned.id)
        elif existing.status != "active":
            skill_service.activate_skill(db, existing.id)

    for item in TA_TOPICS:
        content = (
            f"TA KB [{item['category']}]\n"
            f"{item['name']}: {item['summary']}\n\n"
            f"{item['instructions']}"
        )
        rec = store.record(
            db,
            bot_slug=TRADING_BOT_SLUG,
            kind="ta-kb",
            title=item["name"],
            content=content,
            source_ref=f"ta-kb:{item['slug']}",
            shared=True,
        )
        learning_ids.append(rec.id)

    logger.info(
        "TA KB installed: topics=%s installed=%s refreshed=%s disk=%s",
        len(TA_TOPICS),
        installed,
        refreshed,
        disk,
    )
    return {
        "topic_count": len(TA_TOPICS),
        "categories": list({t["category"] for t in TA_TOPICS}),
        "installed": installed,
        "refreshed": refreshed,
        "learning_ids": learning_ids,
        "disk_path": str(disk),
    }


def build_ta_kb_brief(*, limit: int = 40) -> str:
    lines = ["LOCAL TA KNOWLEDGE BASE (trading-bot):"]
    for item in TA_TOPICS[:limit]:
        lines.append(f"- [{item['category']}] {item['name']}: {item['instructions'][:180]}")
    if len(TA_TOPICS) > limit:
        lines.append(f"... +{len(TA_TOPICS) - limit} more topics in data/trading_ta_kb/")
    return "\n".join(lines)


def format_ta_install_reply(result: dict[str, object], *, web_fetched: int = 0) -> str:
    cats = ", ".join(str(c) for c in (result.get("categories") or []))
    parts = [
        "Technical Analysis KB installed locally:",
        "",
        f"Topics: {result.get('topic_count', 0)} across {cats}",
        f"Skills installed: {len(result.get('installed') or [])}",
        f"Skills refreshed: {len(result.get('refreshed') or [])}",
        f"Local learnings: {len(result.get('learning_ids') or [])}",
        f"Disk: {result.get('disk_path', '')}",
    ]
    if web_fetched:
        parts.append(f"Web IMP notes added this session: {web_fetched}")
    parts.extend(
        [
            "",
            "Covers: all major chart types (line, bar, candle, HA, renko, kagi, P&F, range),",
            "patterns, indicators (RSI, MACD, BB, ADX, VWAP, Ichimoku, Fib), and trade scenarios.",
            "Trading-bot recalls these on chart/trade asks. Not financial advice.",
        ]
    )
    return "\n".join(parts)
