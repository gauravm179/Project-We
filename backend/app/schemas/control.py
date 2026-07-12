from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ControlSessionCreate(BaseModel):
    shared: bool = False
    purpose: str = Field(min_length=3, max_length=1000)
    allow_write: bool = False


class ControlSessionRecord(BaseModel):
    id: int
    purpose: str
    status: str
    allow_screen_read: bool
    allow_write: bool
    created_at: datetime
    ended_at: datetime | None


class AssistRequest(BaseModel):
    task: Literal["email_draft", "form_fill"]
    instruction: str = Field(min_length=3, max_length=5000)
    screen_context: str = Field(min_length=3, max_length=20_000)


class AssistResponse(BaseModel):
    session_id: int
    task: str
    response: str


class ControlActionCreate(BaseModel):
    session_id: int
    action_type: str = Field(min_length=2, max_length=64)
    target: str = Field(min_length=2, max_length=2000)
    payload: str = Field(default="", max_length=20_000)


class ControlActionRecord(BaseModel):
    id: int
    session_id: int
    action_type: str
    target: str
    payload: str
    status: str
    preview: str
    result: str | None
    created_at: datetime
    resolved_at: datetime | None


class ControlActionDecision(BaseModel):
    approve: bool

