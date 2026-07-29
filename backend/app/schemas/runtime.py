from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RuntimeStatus(BaseModel):
    status: str
    uptime_seconds: float
    started_at: datetime
    last_heartbeat: datetime | None = None
    heartbeat_count: int = 0


class HeartbeatRecord(BaseModel):
    id: int
    uptime_seconds: float
    status: str
    recorded_at: datetime
