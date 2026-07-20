from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.voice import VoiceConfigPatch, VoiceStatusResponse
from app.voice.assistant import VoiceAssistant

router = APIRouter(prefix="/voice", tags=["voice"])
voice_assistant = VoiceAssistant()


@router.get("/status", response_model=VoiceStatusResponse)
def voice_status() -> VoiceStatusResponse:
    return VoiceStatusResponse(**voice_assistant.status())


@router.post("/start", response_model=VoiceStatusResponse)
async def voice_start() -> VoiceStatusResponse:
    await voice_assistant.start(get_settings())
    return VoiceStatusResponse(**voice_assistant.status())


@router.post("/stop", response_model=VoiceStatusResponse)
async def voice_stop() -> VoiceStatusResponse:
    await voice_assistant.stop()
    return VoiceStatusResponse(**voice_assistant.status())


@router.patch("/config", response_model=VoiceStatusResponse)
def voice_config(payload: VoiceConfigPatch) -> VoiceStatusResponse:
    voice_assistant.update_config(
        wake_word=payload.wake_word,
        wake_sensitivity=payload.wake_sensitivity,
        stt_model=payload.stt_model,
        tts_voice=payload.tts_voice,
        silence_threshold=payload.silence_threshold,
    )
    return VoiceStatusResponse(**voice_assistant.status())

