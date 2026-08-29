"""Install full TA KB locally + optional bulk fetch from TradingView/Zerodha web."""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy.orm import Session

from app.trading.ta_curriculum import (
    TA_TOPICS,
    format_ta_install_reply,
    install_ta_kb_local,
)
from app.trading.web_learn import TradingWebLearnResult, run_trading_web_learn
from app.web_learning.service import WebLearningService

logger = logging.getLogger(__name__)

_TA_KB_ASK = re.compile(
    r"\b("
    r"install\s+(?:(?:all|full)\s+)?(?:ta|technical)\s*(?:kb|knowledge|analysis|base)?|"
    r"learn\s+all\s+(?:chart|technical|ta)\s*(?:types?|analysis|scenarios?)?|"
    r"fetch\s+all\s+(?:chart|technical|tradingview|ta)|"
    r"all\s+(?:chart\s+)?types?\s+(?:of\s+)?(?:charts?|technical)|"
    r"full\s+(?:ta|technical)\s+(?:kb|database|curriculum)|"
    r"local\s+(?:ta\s+)?(?:db|database|knowledge\s+base)|"
    r"every\s+(?:chart|technical)\s+(?:type|scenario)|"
    r"complete\s+technical\s+analysis\s+(?:course|kb|training)"
    r")\b",
    re.IGNORECASE,
)


def is_ta_kb_install_ask(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _TA_KB_ASK.search(text):
        return True
    # "learn all charts and indicators from tradingview"
    if re.search(r"\b(learn|install|fetch|build)\b", text, re.IGNORECASE) and re.search(
        r"\b(all|every|full|complete)\b", text, re.IGNORECASE
    ) and re.search(
        r"\b(chart|technical|ta|indicator|pattern|tradingview|zerodha|knowledge)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


async def install_full_ta_kb(
    db: Session,
    web: WebLearningService,
    *,
    user_message: str = "",
    fetch_web: bool = True,
    max_web_queries: int = 12,
    max_web_captures: int = 8,
    web_timeout: float = 120.0,
) -> tuple[dict[str, object], TradingWebLearnResult | None]:
    """Install offline TA KB, then optionally bulk-fetch web IMP notes."""
    local = install_ta_kb_local(db)
    web_result: TradingWebLearnResult | None = None

    if not fetch_web or not web.internet_allowed(db):
        return local, web_result

    # Build a comprehensive learn message from all web_query fields (deduped).
    queries = []
    seen: set[str] = set()
    for item in TA_TOPICS:
        q = (item.get("web_query") or "").strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)
        if len(queries) >= max_web_queries:
            break

    learn_msg = user_message or (
        "install all technical analysis learn from TradingView Zerodha "
        + " ".join(queries[:4])
    )
    try:
        web_result = await asyncio.wait_for(
            run_trading_web_learn(
                db,
                web,
                user_message=learn_msg,
                max_queries=min(max_web_queries, len(queries) or 3),
                max_captures=max_web_captures,
            ),
            timeout=web_timeout,
        )
    except asyncio.TimeoutError:
        web_result = TradingWebLearnResult(
            errors=["Web fetch timed out — local TA KB is installed; retry web learn later."]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("TA KB web fetch failed")
        web_result = TradingWebLearnResult(errors=[str(exc)])

    return local, web_result


def format_full_ta_reply(
    local: dict[str, object],
    web: TradingWebLearnResult | None,
    *,
    internet_approved: bool,
) -> str:
    web_saved = len(web.saved) if web else 0
    body = format_ta_install_reply(local, web_fetched=web_saved)

    if not internet_approved:
        body += (
            "\n\nInternet not approved — offline TA KB is ready. "
            "Approve internet and ask again to fetch TradingView/Zerodha pages."
        )
        return body

    if web and web.requires_permission:
        body += f"\n\n{web.message or 'Internet approval required for web fetch.'}"
        return body

    if web and web.saved:
        body += "\n\nWeb IMP notes saved:"
        for note in web.saved[:6]:
            body += f"\n• #{note.learning_id} {note.title}"
    if web and web.errors:
        body += "\n\nWeb fetch notes:"
        for err in web.errors[:3]:
            body += f"\n• {err}"

    return body
