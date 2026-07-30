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

# Short replies after "Approve internet access…"
_AFFIRM_PATTERN = compile(
    r"^\s*("
    r"y|ye|yes|yep|yeah|yea|ok|okay|sure|go\s*ahead|proceed|"
    r"approve(?:d)?|approval|allow(?:ed)?|grant(?:ed)?|confirm(?:ed)?|"
    r"yes[\s,.-]*(?:please|approve(?:d)?|i\s+approve|internet)?|"
    r"(?:i\s+)?(?:approve|allow|grant)(?:\s+internet)?(?:\s+access)?|"
    r"permission\s+granted"
    r")\s*[.!]*\s*$",
    IGNORECASE,
)

_REJECT_PATTERN = compile(
    r"^\s*("
    r"n|no|nope|nah|deny|denied|reject(?:ed)?|cancel(?:led)?|"
    r"do\s+not\s+approve|don'?t\s+approve|never"
    r")\s*[.!]*\s*$",
    IGNORECASE,
)

class PolicyService:
    def message_likely_needs_internet(self, message: str) -> bool:
        return bool(_INTERNET_HINT_PATTERN.search(message))

    def parse_permission_reply(self, message: str) -> bool | None:
        """Return True=approve, False=reject, None=not a permission reply."""
        text = (message or "").strip()
        if not text or len(text) > 80:
            return None
        if _AFFIRM_PATTERN.match(text):
            return True
        if _REJECT_PATTERN.match(text):
            return False
        return None

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

    def latest_pending(
        self, db: Session, capability: str = "internet"
    ) -> PermissionRecord | None:
        row = db.scalar(
            select(PermissionRequest)
            .where(
                PermissionRequest.capability == capability,
                PermissionRequest.status == "pending",
            )
            .order_by(PermissionRequest.id.desc())
        )
        return self._to_record(row) if row else None

    def approve_all_pending(
        self, db: Session, capability: str = "internet"
    ) -> list[PermissionRecord]:
        rows = db.scalars(
            select(PermissionRequest)
            .where(
                PermissionRequest.capability == capability,
                PermissionRequest.status == "pending",
            )
            .order_by(PermissionRequest.id.asc())
        ).all()
        now = datetime.now(timezone.utc)
        approved: list[PermissionRecord] = []
        for row in rows:
            row.status = "approved"
            row.resolved_at = now
            approved.append(self._to_record(row))
        if approved:
            db.flush()
        return approved

    def reject_all_pending(
        self, db: Session, capability: str = "internet"
    ) -> list[PermissionRecord]:
        rows = db.scalars(
            select(PermissionRequest)
            .where(
                PermissionRequest.capability == capability,
                PermissionRequest.status == "pending",
            )
            .order_by(PermissionRequest.id.asc())
        ).all()
        now = datetime.now(timezone.utc)
        rejected: list[PermissionRecord] = []
        for row in rows:
            row.status = "rejected"
            row.resolved_at = now
            rejected.append(self._to_record(row))
        if rejected:
            db.flush()
        return rejected

    def message_from_permission_reason(self, reason: str) -> str | None:
        """Pull the original user ask out of a permission reason string."""
        text = (reason or "").strip()
        # Typical: "... for: <original message>" or "... to read: <url>"
        match = compile(r"(?:for|to\s+read):\s*(.+)$", IGNORECASE).search(text)
        if not match:
            return None
        message = match.group(1).strip()
        return message or None

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
