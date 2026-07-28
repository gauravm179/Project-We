from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SosTriggerRequest(BaseModel):
    reason: str = Field(default="Manual SOS trigger", min_length=3, max_length=1000)


class SafetyStatus(BaseModel):
    emergency_stop_active: bool
    reason: str | None
    triggered_at: datetime | None
    sos_non_removable: bool = True
