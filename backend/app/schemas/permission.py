from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PermissionRequestCreate(BaseModel):
    capability: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=3, max_length=1000)


class PermissionDecision(BaseModel):
    approve: bool


class PermissionRecord(BaseModel):
    id: int
    capability: str
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
