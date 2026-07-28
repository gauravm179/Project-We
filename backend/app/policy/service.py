from __future__ import annotations

from datetime import datetime, timezone
from re import IGNORECASE, compile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PermissionRequest
from app.schemas.permission import PermissionRecord

_INTERNET_HINT_PATTERN = compile(
    r"\b(latest|today|current|news|weather|stock|price|live update|breaking)\b",
    IGNORECASE,
)


class PolicyService:
    def message_likely_needs_internet(self, message: str) -> bool:
        return bool(_INTERNET_HINT_PATTERN.search(message))

    def has_approved_capability(self, db: Session, capability: str) -> bool:
        row = db.scalar(
            select(PermissionRequest)
            .where(
                PermissionRequest.capability == capability,
                PermissionRequest.status == "approved",
            )
            .order_by(PermissionRequest.id.desc())
        )
        return row is not None

    def create_permission_request(self, db: Session, capability: str, reason: str) -> PermissionRecord:
        row = PermissionRequest(
            capability=capability,
            reason=reason,
            status="pending",
        )
        db.add(row)
        db.flush()
        return self._to_record(row)

    def list_permission_requests(self, db: Session, status: str | None = None) -> list[PermissionRecord]:
        stmt = select(PermissionRequest).order_by(PermissionRequest.id.desc())
        if status:
            stmt = stmt.where(PermissionRequest.status == status)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [self._to_record(row) for row in rows]

    def resolve_permission_request(
        self,
        db: Session,
        request_id: int,
        approve: bool,
    ) -> PermissionRecord | None:
        row = db.get(PermissionRequest, request_id)
        if row is None:
            return None
        row.status = "approved" if approve else "rejected"
        row.resolved_at = datetime.now(timezone.utc)
        db.flush()
        return self._to_record(row)

    def _to_record(self, row: PermissionRequest) -> PermissionRecord:
        return PermissionRecord(
            id=row.id,
            capability=row.capability,
            reason=row.reason,
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
