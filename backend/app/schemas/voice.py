from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceConfigPatch(BaseModel):
    wake_word: str | None = Field(default=None, min_length=1, max_length=64)
    wake_sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)
    stt_model: str | None = Field(default=None, min_length=1, max_length=64)
    tts_voice: str | None = Field(default=None, min_length=1, max_length=128)
    silence_threshold: float | None = Field(default=None, ge=0.2, le=10.0)


class VoiceStatusResponse(BaseModel):
    active: bool
    wake_word: str
    wake_sensitivity: float
    stt_model: str
    tts_voice: str
    last_transcript: str
    last_reply: str = ""
    last_error: str | None = None
    deps_ready: bool = False


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=10_000)
    speak: bool = False
    shared: bool = True


class VoiceCommandResponse(BaseModel):
    transcript: str
    reply: str
    requires_permission: bool = False
    permission_request_id: int | None = None
    routed_to: str = "master"
    route_reason: str | None = None
