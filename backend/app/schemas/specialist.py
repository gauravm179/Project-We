from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SpecialistCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    sector: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=1)
    description: str = ""


class SpecialistUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    description: str | None = None
    enabled: bool | None = None


class SpecialistRecord(BaseModel):
    id: int
    slug: str
    name: str
    sector: str
    system_prompt: str
    description: str
    enabled: bool
    created_at: datetime


class SpecialistChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class SpecialistChatReply(BaseModel):
    specialist_slug: str
    specialist_name: str
    response: str


class SpecialistMessageRecord(BaseModel):
    role: str
    content: str
    created_at: datetime
