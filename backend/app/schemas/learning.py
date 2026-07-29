from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MistakeFeedbackRequest(BaseModel):
    mistake: str = Field(min_length=1, max_length=5_000)
    correction: str = Field(min_length=1, max_length=5_000)
    language: str | None = Field(default=None, max_length=64)
    topic: str | None = Field(default=None, max_length=128)


class MistakeLessonRecord(BaseModel):
    id: int
    specialist_slug: str
    mistake: str
    correction: str
    language: str | None = None
    topic: str | None = None
    created_at: datetime


class GuidelineLookupRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=64)
    allow_internet: bool = False


class GuidelineRecord(BaseModel):
    title: str
    source: str
    url: str | None = None
    summary: str
    from_internet: bool = False
