from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np


@dataclass
class VoiceListenerConfig:
    wake_word: str = "ducus"
    wake_sensitivity: float = 0.5
    sample_rate: int = 16_000
    silence_threshold: float = 0.01
    silence_seconds: float = 1.5


class VoiceListener:
    """Always-on microphone listener with wake-word detection."""

    def __init__(self, config: VoiceListenerConfig) -> None:
        self.config = config
        self._oww_model = None
        self._sd = None
        self._load_dependencies()

    def _load_dependencies(self) -> None:
        import sounddevice as sd  # type: ignore

        self._sd = sd

        try:
            from openwakeword.model import Model  # type: ignore

            self._oww_model = Model()
        except Exception:
            # Keep running; explicit error is raised when start() is called.
            self._oww_model = None

    def ensure_ready(self) -> None:
        if self._sd is None:
            raise RuntimeError("sounddevice is unavailable")
        if self._oww_model is None:
            raise RuntimeError(
                "openwakeword model failed to initialize. "
                "Install runtime deps and verify microphone permissions."
            )

    def wait_for_wake_word(self, stop_flag: callable) -> bool:
        """Block until wake word is detected or stop_flag returns True."""
        self.ensure_ready()
        assert self._sd is not None
        assert self._oww_model is not None

        frame_size = 1280  # 80ms at 16kHz
        with self._sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_size,
        ) as stream:
            while not stop_flag():
                audio_chunk, _ = stream.read(frame_size)
                pcm = audio_chunk.flatten().astype(np.int16)
                prediction = self._oww_model.predict(pcm)
                if self._is_wake_hit(prediction):
                    return True
        return False

    def _is_wake_hit(self, prediction: dict[str, float]) -> bool:
        target = self.config.wake_word.lower()
        best_score = 0.0
        for key, score in prediction.items():
            key_l = key.lower()
            if target in key_l and score >= self.config.wake_sensitivity:
                return True
            if score > best_score:
                best_score = score
        # Fallback if custom wake word model name doesn't match expected key.
        return best_score >= max(0.8, self.config.wake_sensitivity + 0.2)

    def record_until_silence(self, max_seconds: float = 20.0) -> np.ndarray:
        self.ensure_ready()
        assert self._sd is not None

        frame_size = 1600  # 100ms
        silence_frames_needed = int(self.config.silence_seconds / 0.1)
        silence_frames = 0
        collected: list[np.ndarray] = []

        start = time.time()
        with self._sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=frame_size,
        ) as stream:
            while time.time() - start < max_seconds:
                chunk, _ = stream.read(frame_size)
                audio = chunk.flatten()
                collected.append(audio)
                rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
                if rms < self.config.silence_threshold:
                    silence_frames += 1
                else:
                    silence_frames = 0
                if silence_frames >= silence_frames_needed and len(collected) > 3:
                    break

        if not collected:
            return np.array([], dtype=np.float32)
        return np.concatenate(collected)

