from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.skill import SkillAssignmentRecord, SkillLearnRequest
from app.schemas.specialist import (
    SpecialistChatReply,
    SpecialistChatRequest,
    SpecialistCreate,
    SpecialistMessageRecord,
    SpecialistRecord,
    SpecialistUpdate,
)
from app.skills.service import SkillService
from app.specialists.service import SpecialistService

router = APIRouter(prefix="/specialists", tags=["specialists"])
_service = SpecialistService()
_skill_service = SkillService()


@router.post("", response_model=SpecialistRecord, status_code=201)
def create_specialist(payload: SpecialistCreate, db: Session = Depends(get_db)):
    record = _service.create(db, payload)
    if not record:
        raise HTTPException(status_code=409, detail="Specialist slug already exists")
    return record


@router.get("", response_model=list[SpecialistRecord])
def list_specialists(db: Session = Depends(get_db)):
    return _service.list_all(db)


@router.get("/{slug}", response_model=SpecialistRecord)
def get_specialist(slug: str, db: Session = Depends(get_db)):
    record = _service.get_by_slug(db, slug)
    if not record:
        raise HTTPException(status_code=404, detail="Specialist not found")
    return record


@router.patch("/{slug}", response_model=SpecialistRecord)
def update_specialist(slug: str, patch: SpecialistUpdate, db: Session = Depends(get_db)):
    record = _service.update(db, slug, patch)
    if not record:
        raise HTTPException(status_code=404, detail="Specialist not found")
    return record


@router.delete("/{slug}", status_code=204)
def delete_specialist(slug: str, db: Session = Depends(get_db)):
    if not _service.delete(db, slug):
        raise HTTPException(status_code=404, detail="Specialist not found")


@router.post("/{slug}/chat", response_model=SpecialistChatReply)
async def specialist_chat(
    slug: str,
    request: SpecialistChatRequest,
    db: Session = Depends(get_db),
):
    reply = await _service.chat(db, slug, request.message)
    if reply is None:
        raise HTTPException(status_code=404, detail="Specialist not found or disabled")
    return reply


@router.get("/{slug}/history", response_model=list[SpecialistMessageRecord])
def specialist_history(slug: str, limit: int = 50, db: Session = Depends(get_db)):
    records = _service.history(db, slug, limit)
    if records is None:
        raise HTTPException(status_code=404, detail="Specialist not found")
    return records


@router.post("/{slug}/skills", response_model=SkillAssignmentRecord, status_code=201)
def teach_specialist_skill(
    slug: str, payload: SkillLearnRequest, db: Session = Depends(get_db)
):
    record = _skill_service.learn_skill(db, specialist_slug=slug, payload=payload)
    if not record:
        raise HTTPException(
            status_code=404,
            detail="Specialist or skill not found, or already learned",
        )
    return record


@router.get("/{slug}/skills", response_model=list[SkillAssignmentRecord])
def list_specialist_skills(slug: str, db: Session = Depends(get_db)):
    return _skill_service.list_assignments(db, specialist_slug=slug)
