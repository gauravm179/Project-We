from __future__ import annotations

from typing import Any


class SpeechToText:
    def __init__(self, model_size: str = "base") -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Install with: pip install -e '.[voice]'"
            ) from exc

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio: Any, sample_rate: int = 16_000) -> str:
        if getattr(audio, "size", 0) == 0:
            return ""
        segments, _ = self._model.transcribe(audio, language="en", vad_filter=True)
        parts = [s.text.strip() for s in segments if s.text.strip()]
        return " ".join(parts).strip()
