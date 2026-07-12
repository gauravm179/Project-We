from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MemoryRecord(BaseModel):
    id: int
    memory_type: str
    key: str
    value: str
    confidence: float
    source: str
    created_at: datetime


class MemorySummary(BaseModel):
    memory_type: str
    count: int
