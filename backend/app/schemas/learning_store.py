from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LearningCreate(BaseModel):
    bot_slug: str = Field(default="master", max_length=64)
    kind: str = Field(default="insight", max_length=32)
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=8000)
    source_ref: str | None = None
    shared: bool = True


class LearningRecordOut(BaseModel):
    id: int
    bot_slug: str
    kind: str
    title: str
    content: str
    source_ref: str | None
    shared: bool
    storage_path: str
    created_at: datetime
