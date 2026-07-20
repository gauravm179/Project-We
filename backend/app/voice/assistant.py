from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass

from app.brain.service import BrainService
from app.core.config import Settings
from app.db.session import get_session_factory
from app.voice.listener import VoiceListener, VoiceListenerConfig
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech

logger = logging.getLogger(__name__)


@dataclass
class VoiceStatus:
    active: bool = False
    wake_word: str = "ducus"
    wake_sensitivity: float = 0.5
    stt_model: str = "base"
    tts_voice: str = "en_US-amy-medium"
    last_transcript: str = ""
    last_error: str | None = None


class VoiceAssistant:
    def __init__(self) -> None:
        self._brain = BrainService()
        self._task: asyncio.Task | None = None
        self._stop_event = threading.Event()
        self._status = VoiceStatus()
        self._overrides: dict[str, str | float] = {}

    def status(self) -> dict:
        return asdict(self._status)

    async def start(self, settings: Settings) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._status.active = True
        self._status.wake_word = str(self._overrides.get("wake_word", settings.voice_wake_word))
        self._status.wake_sensitivity = float(
            self._overrides.get("wake_sensitivity", settings.voice_wake_sensitivity)
        )
        self._status.stt_model = str(self._overrides.get("stt_model", settings.voice_stt_model))
        self._status.tts_voice = str(self._overrides.get("tts_voice", settings.voice_tts_voice))
        self._status.last_error = None
        self._task = asyncio.create_task(self._run_loop(settings))

    def update_config(
        self,
        *,
        wake_word: str | None = None,
        wake_sensitivity: float | None = None,
        stt_model: str | None = None,
        tts_voice: str | None = None,
        silence_threshold: float | None = None,
    ) -> None:
        if wake_word is not None:
            self._overrides["wake_word"] = wake_word
            self._status.wake_word = wake_word
        if wake_sensitivity is not None:
            self._overrides["wake_sensitivity"] = wake_sensitivity
            self._status.wake_sensitivity = wake_sensitivity
        if stt_model is not None:
            self._overrides["stt_model"] = stt_model
            self._status.stt_model = stt_model
        if tts_voice is not None:
            self._overrides["tts_voice"] = tts_voice
            self._status.tts_voice = tts_voice
        if silence_threshold is not None:
            self._overrides["silence_threshold"] = silence_threshold

    async def stop(self) -> None:
        self._stop_event.set()
        self._status.active = False
        if self._task:
            await asyncio.sleep(0)

    async def _run_loop(self, settings: Settings) -> None:
        listener = VoiceListener(
            VoiceListenerConfig(
                wake_word=str(self._overrides.get("wake_word", settings.voice_wake_word)),
                wake_sensitivity=float(
                    self._overrides.get("wake_sensitivity", settings.voice_wake_sensitivity)
                ),
                silence_seconds=float(
                    self._overrides.get("silence_threshold", settings.voice_silence_threshold)
                ),
            )
        )
        stt = SpeechToText(str(self._overrides.get("stt_model", settings.voice_stt_model)))
        tts = TextToSpeech(str(self._overrides.get("tts_voice", settings.voice_tts_voice)))
        session_factory = get_session_factory()

        loop = asyncio.get_running_loop()
        while not self._stop_event.is_set():
            try:
                detected = await loop.run_in_executor(
                    None, lambda: listener.wait_for_wake_word(self._stop_event.is_set)
                )
                if not detected:
                    continue
                tts.speak("Yes?")
                audio = await loop.run_in_executor(None, listener.record_until_silence)
                transcript = await loop.run_in_executor(None, lambda: stt.transcribe(audio))
                transcript = transcript.strip()
                if not transcript:
                    continue

                self._status.last_transcript = transcript
                db = session_factory()
                try:
                    reply = await self._brain.chat(db=db, user_message=transcript)
                finally:
                    db.close()
                tts.speak(reply.response)
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                logger.exception("Voice loop error")
                self._status.last_error = str(exc)
                await asyncio.sleep(1.0)

