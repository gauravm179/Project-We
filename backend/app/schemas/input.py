from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScreenInputRequest(BaseModel):
    shared: bool = False
    content: str = Field(min_length=1, max_length=20_000)
    source: str | None = Field(default=None, max_length=128)


class VoiceInputRequest(BaseModel):
    shared: bool = False
    transcript: str = Field(min_length=1, max_length=20_000)
    source: str | None = Field(default=None, max_length=128)


class InputEventRecord(BaseModel):
    id: int
    input_type: str
    content: str
    source: str | None
    created_at: datetime
