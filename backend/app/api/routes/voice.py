from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.voice import (
    VoiceCommandRequest,
    VoiceCommandResponse,
    VoiceConfigPatch,
    VoiceStatusResponse,
)
from app.voice.assistant import VoiceAssistant

logger = logging.getLogger(__name__)

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
    logger.info("voice/command start: %s", (payload.transcript or "")[:160])
    if not payload.shared:
        raise HTTPException(
            status_code=403,
            detail=(
                "Voice command denied. Check “I share microphone / voice” on the Voice page, "
                "then try again."
            ),
        )
    try:
        result = await voice_assistant.handle_command(payload.transcript, speak=payload.speak)
    except Exception as exc:  # noqa: BLE001 - never leave the UI with an empty failure
        logger.exception("voice/command failed")
        # Return 200 with an actionable reply so the chat panel always shows something.
        return VoiceCommandResponse(
            transcript=payload.transcript,
            reply=(
                "I hit an error while handling that request "
                f"({type(exc).__name__}: {exc}). "
                "If this was a web/learn ask, approve internet (yes approved), then try again. "
                "You can also use http://127.0.0.1:8000/ui/web-learner.html."
            ),
            requires_permission=False,
            permission_request_id=None,
            routed_to="master",
            route_reason=f"voice error: {type(exc).__name__}",
        )
    logger.info(
        "voice/command done routed=%s chars=%s",
        result.get("routed_to"),
        len(result.get("reply") or ""),
    )
    return VoiceCommandResponse(**result)
