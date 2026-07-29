from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.models import SafetyState
from app.schemas.safety import SafetyStatus


class SafetyService:
    def status(self, db: Session) -> SafetyStatus:
        row = self._get_or_create_row(db)
        return SafetyStatus(
            emergency_stop_active=row.emergency_stop_active,
            reason=row.reason,
            triggered_at=row.triggered_at,
        )

    def trigger_sos(self, db: Session, reason: str) -> SafetyStatus:
        row = self._get_or_create_row(db)
        row.emergency_stop_active = True
        row.reason = reason
        row.triggered_at = datetime.now(timezone.utc)
        db.flush()
        return self.status(db)

    def is_emergency_stop_active(self, db: Session) -> bool:
        """Read-only check for middleware. Never insert on the hot path."""
        try:
            row = db.scalar(select(SafetyState).order_by(SafetyState.id.asc()).limit(1))
        except OperationalError:
            # SQLite busy — fail open so polling UI does not 500.
            return False
        if row is None:
            return False
        return bool(row.emergency_stop_active)

    def ensure_initialized(self, db: Session) -> None:
        self._get_or_create_row(db)
        db.commit()

    def _get_or_create_row(self, db: Session) -> SafetyState:
        row = db.scalar(select(SafetyState).order_by(SafetyState.id.asc()).limit(1))
        if row is None:
            row = SafetyState(
                emergency_stop_active=False,
                reason=None,
                triggered_at=None,
            )
            db.add(row)
            db.flush()
        return row
