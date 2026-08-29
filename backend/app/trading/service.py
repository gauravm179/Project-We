"""Trading-bot helpers: grounded analysis from charts + news + webhooks."""

from __future__ import annotations

import re

from app.trading.curriculum import TRADING_METHOD, build_chart_knowledge_brief
from app.trading.intent import extract_tickers
from app.web_learning.service import WebAssistResult


def compose_trading_analysis(
    user_message: str,
    *,
    web_assist: WebAssistResult | None = None,
    webhook_note: str | None = None,
) -> str:
    """Build a structured trading reply without inventing prices."""
    tickers = extract_tickers(user_message)
    msg_l = (user_message or "").lower()
    if webhook_note is None and "trading webhook alert" in msg_l:
        webhook_note = (user_message or "").strip()[:500]

    parts: list[str] = [
        "Trading analysis (chart knowledge + evidence — not financial advice):",
        "",
        "1) Chart read (local skills)",
    ]

    chart_notes: list[str] = []
    if any(w in msg_l for w in ("candle", "candlestick", "ohlc")):
        chart_notes.append(
            "Candles: body=open↔close, wicks=high/low; long wick = rejection, long body = conviction."
        )
    if "heikin" in msg_l:
        chart_notes.append(
            "Heikin-Ashi smooths noise — use for trend persistence, confirm entries on regular candles."
        )
    if any(w in msg_l for w in ("support", "resistance", "breakout", "level")):
        chart_notes.append(
            "Map support/resistance from prior swings; a break needs follow-through, not just a wick."
        )
    if any(w in msg_l for w in ("trend", "uptrend", "downtrend", "hh", "hl", "structure")):
        chart_notes.append(
            "Structure: HH+HL = uptrend, LH+LL = downtrend, overlapping swings = range."
        )
    if any(w in msg_l for w in ("volume", "vwap")):
        chart_notes.append(
            "Volume should confirm breaks; weak volume breakouts fail more often."
        )
    if not chart_notes:
        chart_notes.append(
            "Identify chart type → mark trend structure → mark S/R → only then discuss entries."
        )
        chart_notes.append(
            "Use higher timeframe for bias and lower timeframe for timing when both are available."
        )
    for note in chart_notes:
        parts.append(f"• {note}")

    if tickers:
        parts.append("")
        parts.append(f"Symbols in focus: {', '.join(tickers)}")

    if webhook_note:
        parts.append("")
        parts.append("2) Webhook / alert context")
        parts.append(f"• {webhook_note}")

    news_bits = _news_bits_from_assist(web_assist)
    section_n = 3 if webhook_note else 2
    parts.append("")
    parts.append(f"{section_n}) Company / market news (web evidence)")
    if news_bits:
        parts.extend(news_bits[:6])
    else:
        parts.append(
            "• No live news packet attached this turn. "
            "Approve internet and ask again with a ticker for catalyst context."
        )

    section_n += 1
    parts.append("")
    parts.append(f"{section_n}) Bias & scenarios (not a guarantee)")
    if tickers:
        parts.append(
            f"• Working bias for {tickers[0]}: wait for structure + news alignment before acting."
        )
    else:
        parts.append(
            "• Working bias: follow higher-timeframe structure until invalidation is printed."
        )
    parts.append("• Bullish scenario: hold above support / reclaim resistance with volume.")
    parts.append("• Bearish scenario: lose support / fail breakout and accept back into range.")
    parts.append("• Invalidation: the level or structure break that proves the idea wrong.")

    section_n += 1
    parts.append("")
    parts.append(f"{section_n}) Questions to sharpen the call")
    parts.append("• Which timeframe is the decision chart?")
    parts.append("• What exact level invalidates this idea?")
    if tickers:
        parts.append(f"• Any earnings/news today for {tickers[0]} I should weigh more heavily?")
    else:
        parts.append("• Which ticker/company should I pull news for?")

    parts.append("")
    parts.append("Method reminder: " + TRADING_METHOD.splitlines()[0])
    return "\n".join(parts)


def _news_bits_from_assist(assist: WebAssistResult | None) -> list[str]:
    if assist is None or not (assist.context or "").strip():
        return []
    bits: list[str] = []
    current_title = ""
    for raw in (assist.context or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("WEB LEARNER"):
            continue
        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            current_title = numbered.group(2).strip()
            continue
        if line.startswith("URL:") and current_title:
            url = line.removeprefix("URL:").strip()
            bits.append(f"• {current_title} — {url}")
            current_title = ""
            continue
        if current_title and not line.startswith("URL:"):
            # snippet
            bits.append(f"• {current_title} — {line[:220]}")
            current_title = ""
        if line.startswith("Captured #") or line.startswith("Summary:"):
            bits.append(f"• {line[:260]}")
    return bits


def trading_system_addon() -> str:
    return build_chart_knowledge_brief()
