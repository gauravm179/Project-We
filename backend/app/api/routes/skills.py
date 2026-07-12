from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.skill import (
    SkillAssignmentRecord,
    SkillAssignmentUpdate,
    SkillCreate,
    SkillLearnRequest,
    SkillRecord,
)
from app.skills.service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])
_service = SkillService()


@router.post("", response_model=SkillRecord, status_code=201)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db)):
    record = _service.create_skill(db, payload)
    if not record:
        raise HTTPException(status_code=409, detail="Skill slug already exists")
    return record


@router.get("", response_model=list[SkillRecord])
def list_skills(db: Session = Depends(get_db)):
    return _service.list_skills(db)


@router.get("/{slug}", response_model=SkillRecord)
def get_skill(slug: str, db: Session = Depends(get_db)):
    record = _service.get_skill(db, slug)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    return record


@router.post("/learn", response_model=SkillAssignmentRecord, status_code=201)
def learn_skill_global(payload: SkillLearnRequest, db: Session = Depends(get_db)):
    """Teach a skill to the main bot (no specialist)."""
    record = _service.learn_skill(db, specialist_slug=None, payload=payload)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found or already learned")
    return record


@router.get("/learned/global", response_model=list[SkillAssignmentRecord])
def list_global_learned(db: Session = Depends(get_db)):
    return _service.list_assignments(db, specialist_slug=None)


@router.patch(
    "/assignments/{assignment_id}", response_model=SkillAssignmentRecord
)
def update_assignment(
    assignment_id: int, patch: SkillAssignmentUpdate, db: Session = Depends(get_db)
):
    record = _service.update_assignment(db, assignment_id, patch)
    if not record:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return record


@router.post(
    "/assignments/{assignment_id}/activate",
    response_model=SkillAssignmentRecord,
)
def activate_assignment(assignment_id: int, db: Session = Depends(get_db)):
    record = _service.activate_skill(db, assignment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return record
