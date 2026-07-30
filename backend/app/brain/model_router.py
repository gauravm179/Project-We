from __future__ import annotations

import re
from dataclasses import dataclass
from re import IGNORECASE

_TECHNICAL_PATTERN = re.compile(
    r"\b("
    r"code|coding|program|programming|python|javascript|typescript|java|golang|rust|"
    r"debug|refactor|unit\s*test|write\s+tests?|compile|syntax|algorithm|"
    r"stack\s+trace|exception|bug|fix|sql|regex|api\s+endpoint|"
    r"architecture|concurrency|asyncio|thread(?:ing)?|deadlock|race\s+condition|"
    r"optimize|performance|complexity|big[\s-]?o|memory\s+leak|"
    r"implement|design\s+pattern|microservice|kubernetes|docker|"
    r"deep\s+dive|complex|technical|low[\s-]?level|compiler|"
    r"math(?:s|ematics)?|proof|derive|calculus|linear\s+algebra|"
    r"use\s+deepseek|ask\s+deepseek"
    r")\b",
    IGNORECASE,
)

_CHAT_FORCE_PATTERN = re.compile(
    r"\b("
    r"just\s+chat|quick\s+chat|use\s+qwen|simple\s+question|"
    r"hello|hi\b|hey\b|how\s+are\s+you|good\s+morning|good\s+night|"
    r"thank(?:s| you)|remind\s+me|what(?:'| i)s\s+the\s+time"
    r")\b",
    IGNORECASE,
)


@dataclass(frozen=True)
class ModelChoice:
    tier: str  # "chat" | "tech"
    reason: str


def choose_model_tier(
    message: str,
    *,
    specialist_slug: str | None = None,
) -> ModelChoice:
    """Pick conversation (fast) vs technical (deeper) model tier."""
    text = (message or "").strip()
    slug = (specialist_slug or "").strip().lower()

    if slug in {"coding-bot"}:
        return ModelChoice(tier="tech", reason="coding specialist")

    if slug in {"web-learner-bot"}:
        # Web summaries stay on the fast chat model unless clearly technical.
        if _TECHNICAL_PATTERN.search(text):
            return ModelChoice(tier="tech", reason="technical web question")
        return ModelChoice(tier="chat", reason="web learner conversation")

    if _CHAT_FORCE_PATTERN.search(text) and not _TECHNICAL_PATTERN.search(text):
        return ModelChoice(tier="chat", reason="casual conversation")

    if _TECHNICAL_PATTERN.search(text):
        return ModelChoice(tier="tech", reason="technical/complex request")

    # Longer prompts with code fences are usually technical.
    if "```" in text or text.count("\n") >= 8:
        return ModelChoice(tier="tech", reason="long/code-heavy prompt")

    return ModelChoice(tier="chat", reason="default conversation")
