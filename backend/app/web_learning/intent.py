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
            if query:
                return query
    return None


def message_needs_web_assist(message: str) -> bool:
    return bool(extract_urls(message) or extract_search_query(message))


def is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
