from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class ChatReply(BaseModel):
    response: str


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime
