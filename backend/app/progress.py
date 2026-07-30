from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("app.progress")


@dataclass
class ProgressState:
    busy: bool = False
    step: str = "idle"
    detail: str = ""
    transcript: str = ""
    started_at: float | None = None
    updated_at: float | None = None
    steps: list[str] = field(default_factory=list)


class ProgressTracker:
    """Process-wide step log so Terminal + Voice UI can show long-running work."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = ProgressState()

    def start(self, transcript: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._state = ProgressState(
                busy=True,
                step="started",
                detail="Command received",
                transcript=(transcript or "")[:200],
                started_at=now,
                updated_at=now,
                steps=[],
            )
        self._emit("started", "Command received")

    def step(self, step: str, detail: str = "") -> None:
        now = time.monotonic()
        with self._lock:
            self._state.busy = True
            self._state.step = step
            self._state.detail = detail
            self._state.updated_at = now
            started = self._state.started_at or now
            elapsed = now - started
            line = f"+{elapsed:5.1f}s  [{step}] {detail}".rstrip()
            self._state.steps.append(line)
            # Keep the last N lines for the UI.
            if len(self._state.steps) > 40:
                self._state.steps = self._state.steps[-40:]
        self._emit(step, detail)

    def finish(self, detail: str = "done") -> None:
        now = time.monotonic()
        with self._lock:
            started = self._state.started_at or now
            elapsed = now - started
            self._state.busy = False
            self._state.step = "done"
            self._state.detail = detail
            self._state.updated_at = now
            line = f"+{elapsed:5.1f}s  [done] {detail}"
            self._state.steps.append(line)
        logger.info("PROGRESS +%0.1fs [done] %s", elapsed, detail)

    def fail(self, detail: str) -> None:
        now = time.monotonic()
        with self._lock:
            started = self._state.started_at or now
            elapsed = now - started
            self._state.busy = False
            self._state.step = "error"
            self._state.detail = detail
            self._state.updated_at = now
            line = f"+{elapsed:5.1f}s  [error] {detail}"
            self._state.steps.append(line)
        logger.error("PROGRESS +%0.1fs [error] %s", elapsed, detail)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            started = self._state.started_at
            updated = self._state.updated_at
            now = time.monotonic()
            elapsed = (now - started) if started else 0.0
            return {
                "busy": self._state.busy,
                "step": self._state.step,
                "detail": self._state.detail,
                "transcript": self._state.transcript,
                "elapsed_seconds": round(elapsed, 1),
                "updated_ago_seconds": round(now - updated, 1) if updated else None,
                "steps": list(self._state.steps),
            }

    def _emit(self, step: str, detail: str) -> None:
        with self._lock:
            started = self._state.started_at or time.monotonic()
            elapsed = time.monotonic() - started
        logger.info("PROGRESS +%0.1fs [%s] %s", elapsed, step, detail or "")


progress = ProgressTracker()
