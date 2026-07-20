from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    model: str | None = Field(default=None, description="Override model for this request, e.g. 'deepseek-r1:8b'")
    permission_id: int | None = Field(default=None, description="Approved permission ID to proceed with internet search")


class ChatReply(BaseModel):
    response: str
    requires_permission: bool = False
    required_capability: str | None = None
    permission_request_id: int | None = None
    search_results_used: bool = False


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime
