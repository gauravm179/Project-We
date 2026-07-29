from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.voice import (
    VoiceCommandRequest,
    VoiceCommandResponse,
    VoiceConfigPatch,
    VoiceStatusResponse,
)
from app.voice.assistant import VoiceAssistant

router = APIRouter(prefix="/voice", tags=["voice"])
voice_assistant = VoiceAssistant()


@router.get("/status", response_model=VoiceStatusResponse)
def voice_status() -> VoiceStatusResponse:
    return VoiceStatusResponse(**voice_assistant.status())


@router.post("/start", response_model=VoiceStatusResponse)
async def voice_start() -> VoiceStatusResponse:
    try:
        await voice_assistant.start(get_settings())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


@router.post("/command", response_model=VoiceCommandResponse)
async def voice_command(payload: VoiceCommandRequest) -> VoiceCommandResponse:
    """Process a voice transcript (browser STT or wake-word pipeline)."""
    if not payload.shared:
        raise HTTPException(
            status_code=403,
            detail="Voice command denied. Set shared=true only when user explicitly shares voice.",
        )
    try:
        result = await voice_assistant.handle_command(payload.transcript, speak=payload.speak)
    except Exception as exc:  # pragma: no cover - provider/db errors
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return VoiceCommandResponse(**result)
