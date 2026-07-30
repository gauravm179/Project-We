from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.schemas.voice import (
    VoiceCommandRequest,
    VoiceCommandResponse,
    VoiceConfigPatch,
    VoiceStatusResponse,
)
from app.voice.assistant import VoiceAssistant
from app.web_learning.chart_curriculum import format_install_reply, install_chart_curriculum
from app.learning.local_store import LocalLearningStore, is_shared_learning_policy_ask
from app.web_learning.intent import (
    is_chart_curriculum_ask,
    is_chart_learn_ask,
    local_chart_lesson,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])
voice_assistant = VoiceAssistant()


def _safe_json(payload: dict[str, Any]) -> JSONResponse:
    """Always return HTTP 200 JSON, even if encoding is awkward."""
    try:
        return JSONResponse(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("JSONResponse failed: %s", exc)
        return JSONResponse(
            {
                "transcript": str(payload.get("transcript") or ""),
                "reply": f"Response encoding error: {exc}",
                "requires_permission": False,
                "permission_request_id": None,
                "routed_to": "master",
                "route_reason": "json-encode-error",
            }
        )


def _ok_payload(**kwargs: object) -> dict[str, object]:
    """Build a VoiceCommandResponse dict without raising on odd values."""
    try:
        data = VoiceCommandResponse(**kwargs).model_dump()  # type: ignore[arg-type]
        return {
            "transcript": str(data.get("transcript") or ""),
            "reply": str(data.get("reply") or ""),
            "requires_permission": bool(data.get("requires_permission")),
            "permission_request_id": data.get("permission_request_id"),
            "routed_to": str(data.get("routed_to") or "master"),
            "route_reason": (
                str(data.get("route_reason")) if data.get("route_reason") is not None else None
            ),
        }
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


@router.get("/status")
def voice_status() -> JSONResponse:
    try:
        data = voice_assistant.status()
        return JSONResponse(VoiceStatusResponse(**data).model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice/status failed")
        return JSONResponse(
            {
                "active": False,
                "wake_word": "hey jarvis",
                "wake_sensitivity": 0.5,
                "stt_model": "base",
                "tts_voice": "en_US-amy-medium",
                "last_transcript": "",
                "last_reply": "",
                "last_error": str(exc),
                "deps_ready": False,
                "stt_ready": False,
                "deps": {},
                "python_hint": None,
                "progress": {"busy": False, "step": "status-error", "detail": str(exc), "steps": []},
            }
        )


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
async def voice_command(request: Request) -> JSONResponse:
    """Process a voice/text command. Always returns HTTP 200 with a chat reply."""
    logger.info("voice/command ENTER path=%s", request.url.path)
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        return _safe_json(
            _ok_payload(
                transcript="",
                reply=f"Could not read request JSON ({exc}).",
                route_reason="bad-json",
            )
        )

    try:
        payload = VoiceCommandRequest.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        return _safe_json(
            _ok_payload(
                transcript=str((body or {}).get("transcript") or ""),
                reply=f"Invalid voice command payload ({exc}).",
                route_reason="bad-payload",
            )
        )

    transcript = (payload.transcript or "").strip()
    logger.info("voice/command start: %s", transcript[:160])

    if not payload.shared:
        return _safe_json(
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
        return _safe_json(
            _ok_payload(
                transcript="",
                reply="Empty question — type something and ask again.",
                routed_to="master",
                route_reason="empty",
            )
        )

    # Shared local learning for all bots (disk + SQLite recall next time).
    if is_shared_learning_policy_ask(transcript):
        logger.info("voice/command shared-local-learning-enable")
        from app.db.session import get_session_factory

        db = get_session_factory()()
        try:
            store = LocalLearningStore()
            result = store.enable_for_all_bots(db)
            reply = store.format_enable_reply(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("shared learning enable failed")
            reply = (
                f"Could not enable shared local learning ({type(exc).__name__}: {exc}). "
                "Check data/ permissions and try again."
            )
        finally:
            db.close()
        return _safe_json(
            _ok_payload(
                transcript=transcript,
                reply=reply,
                requires_permission=False,
                permission_request_id=None,
                routed_to="master",
                route_reason="shared local learning enabled",
            )
        )

    # Curriculum setup: install multi-chart skills locally (disk + SQLite).
    if is_chart_curriculum_ask(transcript):
        logger.info("voice/command chart-curriculum-install")
        from app.db.session import get_session_factory

        db = get_session_factory()()
        try:
            result = install_chart_curriculum(db)
            reply = "[via Web Learner] " + format_install_reply(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("chart curriculum install failed")
            reply = (
                "[via Web Learner] Could not finish installing the chart curriculum "
                f"({type(exc).__name__}: {exc}). Check data/ permissions and try again."
            )
        finally:
            db.close()
        return _safe_json(
            _ok_payload(
                transcript=transcript,
                reply=reply,
                requires_permission=False,
                permission_request_id=None,
                routed_to="web-learner-bot",
                route_reason="local chart curriculum install",
            )
        )

    # Instant path: chart/TradingView teaching never touches web/Ollama.
    # This avoids Mac hangs that surfaced as HTTP 500 with no POST access log.
    if is_chart_learn_ask(transcript):
        logger.info("voice/command fast-chart-lesson")
        reply = "[via Web Learner] " + local_chart_lesson(transcript)
        return _safe_json(
            _ok_payload(
                transcript=transcript,
                reply=reply,
                requires_permission=False,
                permission_request_id=None,
                routed_to="web-learner-bot",
                route_reason="fast local chart lesson",
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
        return _safe_json(payload_out)
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice/command failed")
        return _safe_json(
            _ok_payload(
                transcript=transcript,
                reply=(
                    "I hit an error while handling that request "
                    f"({type(exc).__name__}: {exc}). "
                    "Try again, or open http://127.0.0.1:8000/ui/web-learner.html"
                ),
                routed_to="master",
                route_reason=f"voice error: {type(exc).__name__}",
            )
        )
