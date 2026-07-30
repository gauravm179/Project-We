from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass

from app.brain.service import BrainService
from app.core.config import Settings
from app.db.session import get_session_factory
from app.inputs.service import InputService
from app.voice.listener import VoiceListener, VoiceListenerConfig
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech

logger = logging.getLogger(__name__)


@dataclass
class VoiceStatus:
    active: bool = False
    wake_word: str = "hey jarvis"
    wake_sensitivity: float = 0.5
    stt_model: str = "base"
    tts_voice: str = "en_US-amy-medium"
    last_transcript: str = ""
    last_reply: str = ""
    last_error: str | None = None
    deps_ready: bool = False


class VoiceAssistant:
    def __init__(self) -> None:
        self._brain = BrainService()
        self._inputs = InputService()
        self._task: asyncio.Task | None = None
        self._stop_event = threading.Event()
        self._status = VoiceStatus()
        self._overrides: dict[str, str | float] = {}

    def _check_deps_ready(self) -> bool:
        """Wake-word mic stack ready (ONNX + openwakeword + sounddevice)."""
        try:
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
            import openwakeword  # noqa: F401
            import onnxruntime  # noqa: F401
        except ImportError:
            return False
        return True

    def _check_stt_ready(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def deps_report(self) -> dict[str, bool]:
        report: dict[str, bool] = {}
        for name in (
            "numpy",
            "sounddevice",
            "openwakeword",
            "onnxruntime",
            "faster_whisper",
        ):
            try:
                __import__(name)
                report[name] = True
            except ImportError:
                report[name] = False
        return report

    def status(self) -> dict:
        from app.progress import progress

        data = asdict(self._status)
        data["deps_ready"] = self._check_deps_ready()
        data["stt_ready"] = self._check_stt_ready()
        data["deps"] = self.deps_report()
        data["python_hint"] = (
            "Python 3.11 or 3.12 recommended for wake-word "
            "(onnxruntime/faster-whisper often missing on 3.14)."
        )
        data["progress"] = progress.snapshot()
        return data

    async def start(self, settings: Settings) -> None:
        if self._task and not self._task.done():
            return
        if not self._check_deps_ready():
            self._status.active = False
            missing = [k for k, ok in self.deps_report().items() if not ok and k != "faster_whisper"]
            raise RuntimeError(
                "Wake-word mic packages missing"
                + (f" ({', '.join(missing)})" if missing else "")
                + ". On Python 3.14, onnxruntime/openwakeword are unavailable — "
                "use Python 3.12 (`pip install -e '.[voice-wake,voice-stt]'`) "
                "or browser 'Start listening' / type a question on /ui/voice.html."
            )
        if not self._check_stt_ready():
            self._status.active = False
            raise RuntimeError(
                "Speech-to-text (faster-whisper) is missing. On Mac:\n"
                "  brew install ffmpeg\n"
                "  pip install -e '.[voice-stt]'\n"
                "Prefer Python 3.12 if pip cannot find wheels. "
                "Meanwhile use browser 'Start listening' or type a question."
            )

        self._stop_event.clear()
        self._status.active = True
        self._status.wake_word = str(self._overrides.get("wake_word", settings.voice_wake_word))
        self._status.wake_sensitivity = float(
            self._overrides.get("wake_sensitivity", settings.voice_wake_sensitivity)
        )
        self._status.stt_model = str(self._overrides.get("stt_model", settings.voice_stt_model))
        self._status.tts_voice = str(self._overrides.get("tts_voice", settings.voice_tts_voice))
        self._status.last_error = None
        self._status.deps_ready = True
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
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def handle_command(self, transcript: str, *, speak: bool = False) -> dict:
        """Process a spoken/typed command through the master bot."""
        from app.progress import progress

        text = transcript.strip()
        if not text:
            return {
                "transcript": "",
                "reply": "Empty question — type something and ask again.",
                "requires_permission": False,
                "permission_request_id": None,
                "routed_to": "master",
                "route_reason": "empty",
            }

        progress.start(text)
        self._status.last_transcript = text
        session_factory = get_session_factory()
        db = session_factory()
        response = ""
        requires_permission = False
        permission_request_id = None
        routed_to = "master"
        route_reason = "master"
        try:
            progress.step("ingest", "Saving voice/text input")
            self._inputs.ingest_voice(db=db, transcript=text, source="voice-command")
            progress.step("brain", "Master bot routing / answering")
            reply = await self._brain.chat(db=db, user_message=text)
            response = reply.response or ""
            requires_permission = bool(reply.requires_permission)
            permission_request_id = reply.permission_request_id
            routed_to = reply.routed_to or "master"
            route_reason = reply.route_reason or routed_to
            self._status.last_reply = response
            try:
                db.commit()
            except Exception:  # noqa: BLE001
                # Brain/specialist paths often commit already; ignore redundant commit issues.
                db.rollback()
            progress.finish(f"routed={routed_to} reply_chars={len(response)}")
        except Exception as exc:
            db.rollback()
            self._status.last_error = str(exc)
            logger.exception("handle_command failed")
            progress.fail(f"{type(exc).__name__}: {exc}")
            response = (
                "I hit an error while handling that request "
                f"({type(exc).__name__}: {exc}). "
                "If this needs the web, type: yes approved  then ask again."
            )
            route_reason = f"handle_command error: {type(exc).__name__}"
        finally:
            db.close()

        if speak and response:
            try:
                progress.step("tts", "Speaking reply")
                tts = TextToSpeech(self._status.tts_voice)
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: tts.speak(response)
                )
            except Exception:  # noqa: BLE001
                logger.exception("TTS speak failed")

        return {
            "transcript": text,
            "reply": response,
            "requires_permission": requires_permission,
            "permission_request_id": permission_request_id,
            "routed_to": routed_to,
            "route_reason": route_reason,
        }

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

                result = await self.handle_command(transcript, speak=False)
                tts.speak(result["reply"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                logger.exception("Voice loop error")
                self._status.last_error = str(exc)
                await asyncio.sleep(1.0)
