from __future__ import annotations

import numpy as np


class SpeechToText:
    def __init__(self, model_size: str = "base") -> None:
        from faster_whisper import WhisperModel  # type: ignore

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16_000) -> str:
        if audio.size == 0:
            return ""
        # faster-whisper accepts float32 mono arrays in range [-1,1]
        segments, _ = self._model.transcribe(audio, language="en", vad_filter=True)
        parts = [s.text.strip() for s in segments if s.text.strip()]
        return " ".join(parts).strip()

