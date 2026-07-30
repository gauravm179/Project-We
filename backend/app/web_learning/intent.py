from __future__ import annotations

import re
from re import IGNORECASE
from urllib.parse import urlparse

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", IGNORECASE)
_SEARCH_PATTERN = re.compile(
    r"(?:^|\b)(?:search(?:\s+the\s+web|\s+online|\s+for)?|google|look\s+up|find\s+online)\s*[:\-]?\s*(.+)$",
    IGNORECASE,
)
_SEARCH_FOR_PATTERN = re.compile(
    r"\bsearch\s+for\s+(.+?)(?:\s+on\s+(?:google|the\s+web|internet))?\s*$",
    IGNORECASE,
)
_LEARN_INTENT_PATTERN = re.compile(
    r"\b(learn|teach(?:\s+me)?|explain|how\s+to\s+read|tutorial|guide)\b",
    IGNORECASE,
)
_FILLER_PATTERN = re.compile(
    r"\b("
    r"can\s+you|could\s+you|please|go\s+though|go\s+through|use\s+the\s+web\s+bot|"
    r"web\s+bot|website|this\s+site|the\s+page|and\s+learn"
    r")\b",
    IGNORECASE,
)


def extract_urls(message: str) -> list[str]:
    found: list[str] = []
    for match in _URL_PATTERN.findall(message):
        url = match.rstrip(".,);]")
        if url not in found:
            found.append(url)
    return found


def extract_search_query(message: str) -> str | None:
    text = message.strip()
    for pattern in (_SEARCH_FOR_PATTERN, _SEARCH_PATTERN):
        match = pattern.search(text)
        if match:
            query = match.group(1).strip(" .?!")
            # Drop trailing URLs from the query text
            query = _URL_PATTERN.sub(" ", query)
            query = re.sub(r"\s+", " ", query).strip(" .?!")
            if query:
                return query

    # "learn how to read trade charts" + a URL → search educational pages
    # (JS chart apps like TradingView don't yield useful HTML text alone).
    urls = extract_urls(text)
    if urls and _LEARN_INTENT_PATTERN.search(text):
        topic = text
        for url in urls:
            topic = topic.replace(url, " ")
        topic = _FILLER_PATTERN.sub(" ", topic)
        topic = re.sub(r"\s+", " ", topic).strip(" .?!")
        if len(topic) >= 8:
            host = urlparse(urls[0]).netloc.replace("www.", "")
            if "tradingview" in host.lower() or "chart" in topic.lower():
                return f"how to read candlestick trading charts beginners {topic}"
            return f"{topic} tutorial guide"
    return None


def is_learn_intent(message: str) -> bool:
    return bool(_LEARN_INTENT_PATTERN.search(message or ""))


def is_chart_learn_ask(message: str) -> bool:
    """True for 'learn to read charts' / TradingView teaching asks."""
    text = (message or "").lower()
    if not is_learn_intent(text):
        return False
    return any(
        key in text
        for key in (
            "chart",
            "charts",
            "candlestick",
            "candle",
            "tradingview",
            "trade chart",
            "price chart",
            "forex chart",
            "stock chart",
        )
    )


def message_needs_web_assist(message: str) -> bool:
    return bool(extract_urls(message) or extract_search_query(message))


def is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
