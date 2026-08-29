"""Trading-bot intents: tickers, news asks, chart/trade routing helpers."""

from __future__ import annotations

import re
from re import IGNORECASE

# Common tickers + generic $TICKER / exchange:SYMBOL patterns.
_TICKER_PATTERN = re.compile(
    r"(?:\$([A-Z]{1,5})\b)|(?:\b(?:NASDAQ|NYSE|NSE|BSE|CRYPTO)[:\s-]?([A-Z]{1,10})\b)|"
    r"\b(AAPL|MSFT|GOOGL|GOOG|AMZN|META|TSLA|NVDA|AMD|NFLX|JPM|BAC|XOM|CVX|"
    r"RELIANCE|TCS|INFY|HDFCBANK|BTC|ETH|SPY|QQQ|NIFTY|BANKNIFTY)\b",
    IGNORECASE,
)

_COMPANY_NEWS_PATTERN = re.compile(
    r"\b("
    r"news|headline|earnings|guidance|lawsuit|fda|merger|acquisition|"
    r"catalyst|sentiment|press\s+release|fundamentals?"
    r")\b",
    IGNORECASE,
)

_TRADING_ASK_PATTERN = re.compile(
    r"\b("
    r"trad(?:e|ing|er)|stock|equity|equities|forex|crypto|ticker|symbol|"
    r"candlestick|heikin|ohlc|support|resistance|breakout|pullback|"
    r"long\s+setup|short\s+setup|buy\s+setup|sell\s+setup|"
    r"entry|stop[\s-]?loss|take[\s-]?profit|risk[\s/]?reward|"
    r"chart\s+(?:read|analysis|setup)|technical\s+analysis|"
    r"tradingview|zerodha|varsity|webhook|alert\s+fired|price\s+action|"
    r"predict|prediction|outlook|bias|"
    r"trading[\s-]?bot|ask\s+(?:the\s+)?trading"
    r")\b",
    IGNORECASE,
)


def is_trading_ask(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _TRADING_ASK_PATTERN.search(text):
        return True
    return bool(extract_tickers(text))


def extract_tickers(message: str) -> list[str]:
    found: list[str] = []
    for match in _TICKER_PATTERN.finditer(message or ""):
        raw = next((g for g in match.groups() if g), "")
        ticker = raw.upper().strip()
        if ticker and ticker not in found:
            found.append(ticker)
    return found


def wants_company_news(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _COMPANY_NEWS_PATTERN.search(text):
        return True
    # Ticker + analyze/predict/trade → pull news automatically.
    return bool(extract_tickers(text)) and is_trading_ask(text)


def company_news_query(message: str) -> str | None:
    tickers = extract_tickers(message)
    if not tickers:
        if wants_company_news(message):
            cleaned = re.sub(r"\s+", " ", message).strip()[:120]
            return f"{cleaned} stock market news today"
        return None
    primary = tickers[0]
    return f"{primary} stock company news earnings catalyst today"


def format_webhook_as_user_message(payload: dict) -> str:
    """Turn a TradingView/generic webhook into a trading-bot chat prompt."""
    ticker = (
        str(payload.get("ticker") or payload.get("symbol") or payload.get("Ticker") or "")
        .strip()
        .upper()
    )
    action = str(
        payload.get("action")
        or payload.get("side")
        or payload.get("order")
        or payload.get("strategy.order.action")
        or ""
    ).strip()
    price = payload.get("price") or payload.get("close") or payload.get("Price")
    interval = payload.get("interval") or payload.get("timeframe") or payload.get("tf")
    message = payload.get("message") or payload.get("text") or payload.get("comment") or ""

    parts = ["Trading webhook alert received."]
    if ticker:
        parts.append(f"Symbol: {ticker}.")
    if action:
        parts.append(f"Signal/action: {action}.")
    if price is not None and str(price).strip():
        parts.append(f"Price: {price}.")
    if interval:
        parts.append(f"Timeframe: {interval}.")
    if message:
        parts.append(f"Note: {message}.")
    parts.append(
        "Analyze this using chart-reading skills and current company news if available. "
        "Give bias, key levels, risks, and what would invalidate the idea. "
        "Do not guarantee profits."
    )
    return " ".join(parts)
