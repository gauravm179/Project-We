from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCandidate:
    memory_type: str
    key: str
    value: str
    confidence: float
    source: str = "user"


_NAME_PATTERN = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z .'-]{0,60})\b", re.IGNORECASE)
_OS_PATTERN = re.compile(
    r"\b(i use|i am using|i'm using|my preferred os is)\s+(mac(?:\s?os)?|windows|linux)\b",
    re.IGNORECASE,
)
_PREFERENCE_PATTERN = re.compile(r"\b(i prefer|i like)\s+([^.!?\n]{2,120})", re.IGNORECASE)
_TASK_PATTERN = re.compile(r"\b(remind me to|todo:?|to do:?|task:)\s+([^.!?\n]{2,200})", re.IGNORECASE)


def extract_memories(message: str) -> list[MemoryCandidate]:
    text = message.strip()
    if not text:
        return []

    candidates: list[MemoryCandidate] = []

    name_match = _NAME_PATTERN.search(text)
    if name_match:
        candidates.append(
            MemoryCandidate(
                memory_type="fact",
                key="user_name",
                value=name_match.group(1).strip(),
                confidence=0.99,
            )
        )

    os_match = _OS_PATTERN.search(text)
    if os_match:
        os_value = os_match.group(2).strip().lower().replace(" ", "")
        normalized_os = "macos" if os_value in {"macos", "mac"} else os_value
        candidates.append(
            MemoryCandidate(
                memory_type="preference",
                key="preferred_os",
                value=normalized_os,
                confidence=0.95,
            )
        )

    pref_match = _PREFERENCE_PATTERN.search(text)
    if pref_match:
        preference_value = pref_match.group(2).strip(" .")
        if preference_value:
            candidates.append(
                MemoryCandidate(
                    memory_type="preference",
                    key="stated_preference",
                    value=preference_value,
                    confidence=0.8,
                )
            )

    task_match = _TASK_PATTERN.search(text)
    if task_match:
        task_value = task_match.group(2).strip(" .")
        if task_value:
            candidates.append(
                MemoryCandidate(
                    memory_type="task",
                    key="pending_task",
                    value=task_value,
                    confidence=0.92,
                )
            )

    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[MemoryCandidate] = []
    for candidate in candidates:
        signature = (
            candidate.memory_type,
            candidate.key,
            candidate.value.casefold(),
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(candidate)
    return unique
