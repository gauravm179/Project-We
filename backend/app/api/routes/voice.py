from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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


def _ok_payload(**kwargs: object) -> dict[str, object]:
    """Build a VoiceCommandResponse dict without raising on odd values."""
    try:
        return VoiceCommandResponse(**kwargs).model_dump()  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Voice response schema fallback: %s", exc)
        return {
            "transcript": str(kwargs.get("transcript") or ""),
            "reply": str(kwargs.get("reply") or f"Internal response error: {exc}"),
            "requires_permission": False,
            "permission_request_id": None,
            "routed_to": "master",
            "route_reason": "response-fallback",
        }


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


@router.post("/command")
async def voice_command(payload: VoiceCommandRequest) -> JSONResponse:
    """Process a voice/text command. Always returns HTTP 200 with a chat reply."""
    transcript = (payload.transcript or "").strip()
    logger.info("voice/command start: %s", transcript[:160])

    if not payload.shared:
        return JSONResponse(
            _ok_payload(
                transcript=transcript,
                reply=(
                    "Voice/text sharing is off. Check “I share microphone / voice”, "
                    "then ask again."
                ),
                routed_to="master",
                route_reason="shared=false",
            )
        )

    if not transcript:
        return JSONResponse(
            _ok_payload(
                transcript="",
                reply="Empty question — type something and ask again.",
                routed_to="master",
                route_reason="empty",
            )
        )

    try:
        result = await voice_assistant.handle_command(transcript, speak=payload.speak)
        payload_out = _ok_payload(**result)
        logger.info(
            "voice/command done routed=%s chars=%s",
            payload_out.get("routed_to"),
            len(str(payload_out.get("reply") or "")),
        )
        return JSONResponse(payload_out)
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice/command failed")
        return JSONResponse(
            _ok_payload(
                transcript=transcript,
                reply=(
                    "I hit an error while handling that request "
                    f"({type(exc).__name__}: {exc}). "
                    "Try: yes approved  then ask again. "
                    "Or open http://127.0.0.1:8000/ui/web-learner.html"
                ),
                routed_to="master",
                route_reason=f"voice error: {type(exc).__name__}",
            )
        )
