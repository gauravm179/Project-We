from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.policy.service import PolicyService
from app.schemas.permission import PermissionDecision, PermissionRecord, PermissionRequestCreate

router = APIRouter(prefix="/permissions", tags=["permissions"])
policy_service = PolicyService()


@router.get("", response_model=list[PermissionRecord])
def list_permission_requests(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PermissionRecord]:
    return policy_service.list_permission_requests(db=db, status=status)


@router.post("", response_model=PermissionRecord)
def create_permission_request(
    payload: PermissionRequestCreate,
    db: Session = Depends(get_db),
) -> PermissionRecord:
    record = policy_service.create_permission_request(
        db=db,
        capability=payload.capability,
        reason=payload.reason,
    )
    db.commit()
    return record


@router.post("/{request_id}/decision", response_model=PermissionRecord)
def decide_permission_request(
    request_id: int,
    payload: PermissionDecision,
    db: Session = Depends(get_db),
) -> PermissionRecord:
    record = policy_service.resolve_permission_request(
        db=db,
        request_id=request_id,
        approve=payload.approve,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Permission request not found")
    db.commit()
    return record
