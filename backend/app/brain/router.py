from __future__ import annotations

import re
from dataclasses import dataclass
from re import IGNORECASE

from app.web_learning.intent import message_needs_web_assist

_CODING_PATTERN = re.compile(
    r"\b("
    r"code|coding|program|programming|python|javascript|typescript|java|golang|rust|"
    r"debug|refactor|unit\s*test|write\s+tests?|compile|syntax|function|class|"
    r"algorithm|binary\s+tree|leetcode|pull\s+request|git\s+commit|"
    r"stack\s+trace|exception|bug|fix|api\s+endpoint|sql|regex|"
    r"coding[\s-]?bot|ask\s+(the\s+)?coding"
    r")\b",
    IGNORECASE,
)

_WEB_LEARNER_PATTERN = re.compile(
    r"\b("
    r"web[\s-]?learner|capture\s+(this\s+)?(page|url)|read\s+(this\s+)?(page|website|url)|"
    r"browse|open\s+the\s+(page|site|url)|what\s+did\s+we\s+learn\s+from\s+(the\s+)?web|"
    r"stored\s+captures?|recall\s+(stored\s+)?pages?"
    r")\b",
    IGNORECASE,
)

_EXPLICIT_SPECIALIST = re.compile(
    r"\b(?:ask|tell|use|call|send\s+to)\s+(?:the\s+)?"
    r"(coding(?:[\s-]?bot)?|web(?:[\s-]?learner)?(?:[\s-]?bot)?|master(?:[\s-]?bot)?)\b",
    IGNORECASE,
)

_MASTER_OVERRIDE = re.compile(
    r"\b(master[\s-]?bot|general\s+assistant|just\s+you)\b",
    IGNORECASE,
)


@dataclass(frozen=True)
class RouteDecision:
    target: str  # "master" | specialist slug
    reason: str


def route_message(message: str) -> RouteDecision:
    """Pick master or a specialist for a chat/voice command."""
    text = message.strip()
    if not text:
        return RouteDecision(target="master", reason="empty")

    explicit = _EXPLICIT_SPECIALIST.search(text)
    if explicit:
        name = explicit.group(1).lower().replace(" ", "-").replace("_", "-")
        if "coding" in name:
            return RouteDecision(target="coding-bot", reason="explicit coding specialist")
        if "web" in name:
            return RouteDecision(target="web-learner-bot", reason="explicit web specialist")
        if "master" in name:
            return RouteDecision(target="master", reason="explicit master")

    if _MASTER_OVERRIDE.search(text):
        return RouteDecision(target="master", reason="master override")

    if _WEB_LEARNER_PATTERN.search(text) or message_needs_web_assist(text):
        return RouteDecision(target="web-learner-bot", reason="web search or URL")

    if _CODING_PATTERN.search(text):
        return RouteDecision(target="coding-bot", reason="coding/logic request")

    return RouteDecision(target="master", reason="default master")
