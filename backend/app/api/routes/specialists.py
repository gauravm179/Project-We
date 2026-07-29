from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.coding.capabilities import BUILD_CAPABILITIES, LOGIC_CAPABILITIES, SUPPORTED_LANGUAGES
from app.db.session import get_db
from app.learning.service import LearningService
from app.schemas.coding import CodingBotCapabilities, LanguageCapability
from app.schemas.learning import MistakeFeedbackRequest, MistakeLessonRecord
from app.schemas.skill import SkillAssignmentRecord, SkillLearnRequest
from app.schemas.specialist import (
    SpecialistChatReply,
    SpecialistChatRequest,
    SpecialistCreate,
    SpecialistMessageRecord,
    SpecialistRecord,
    SpecialistUpdate,
)
from app.schemas.web_learning import WebCaptureDetail, WebCaptureRecord, WebCaptureRequest, WebCaptureResponse
from app.skills.service import SkillService
from app.specialists.service import SpecialistService
from app.web_learning.service import WebLearningService

router = APIRouter(prefix="/specialists", tags=["specialists"])
_service = SpecialistService()
_skill_service = SkillService()
_learning_service = LearningService()
_web_learning_service = WebLearningService()
WEB_LEARNER_SLUG = "web-learner-bot"


@router.post("", response_model=SpecialistRecord, status_code=201)
def create_specialist(payload: SpecialistCreate, db: Session = Depends(get_db)):
    record = _service.create(db, payload)
    if not record:
        raise HTTPException(status_code=409, detail="Specialist slug already exists")
    return record


@router.get("", response_model=list[SpecialistRecord])
def list_specialists(db: Session = Depends(get_db)):
    return _service.list_all(db)


@router.get("/coding-bot/capabilities", response_model=CodingBotCapabilities)
def coding_bot_capabilities(db: Session = Depends(get_db)):
    record = _service.get_by_slug(db, "coding-bot")
    if not record:
        raise HTTPException(status_code=404, detail="Coding bot not found")

    active_skills = _skill_service.list_assignments(db, specialist_slug="coding-bot")
    trained = [skill.skill_slug for skill in active_skills if skill.status == "active"]

    return CodingBotCapabilities(
        slug=record.slug,
        name=record.name,
        sector=record.sector,
        languages=[LanguageCapability(**lang) for lang in SUPPORTED_LANGUAGES],
        logic_capabilities=list(LOGIC_CAPABILITIES),
        build_capabilities=list(BUILD_CAPABILITIES),
        trained_skills=trained,
        browser_ui="/ui/",
    )


@router.get("/web-learner-bot/captures", response_model=list[WebCaptureRecord])
def list_web_captures(db: Session = Depends(get_db), limit: int = 50):
    if _service.get_by_slug(db, WEB_LEARNER_SLUG) is None:
        raise HTTPException(status_code=404, detail="Web learner bot not found")
    return _web_learning_service.list_captures(db, WEB_LEARNER_SLUG, limit=limit)


@router.get("/web-learner-bot/captures/{capture_id}", response_model=WebCaptureDetail)
def get_web_capture(capture_id: int, db: Session = Depends(get_db)):
    record = _web_learning_service.get_capture(db, WEB_LEARNER_SLUG, capture_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    return record


@router.post("/web-learner-bot/capture")
async def capture_web_page(payload: WebCaptureRequest, db: Session = Depends(get_db)):
    if _service.get_by_slug(db, WEB_LEARNER_SLUG) is None:
        raise HTTPException(status_code=404, detail="Web learner bot not found")

    result = await _web_learning_service.capture_url(
        db,
        WEB_LEARNER_SLUG,
        str(payload.url),
        max_images=payload.max_images,
    )
    if isinstance(result, dict):
        if result.get("requires_permission"):
            return result
        if result.get("error"):
            raise HTTPException(status_code=400, detail=str(result["error"]))
        raise HTTPException(status_code=400, detail="Capture failed")

    return WebCaptureResponse(
        capture_id=result.capture_id,
        url=result.url,
        title=result.title,
        text_chars=result.text_chars,
        image_count=result.image_count,
        compressed_bytes=result.compressed_bytes,
        summary=result.summary,
        message=(
            f"Stored compressed learning locally at data/web_learning/captures/{result.capture_id}/"
        ),
    )


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


@router.post("/{slug}/feedback", response_model=MistakeLessonRecord, status_code=201)
def record_mistake_feedback(
    slug: str, payload: MistakeFeedbackRequest, db: Session = Depends(get_db)
):
    record = _learning_service.record_mistake(db, specialist_slug=slug, payload=payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Specialist not found")
    return record


@router.get("/{slug}/lessons", response_model=list[MistakeLessonRecord])
def list_mistake_lessons(slug: str, limit: int = 50, db: Session = Depends(get_db)):
    if _service.get_by_slug(db, slug) is None:
        raise HTTPException(status_code=404, detail="Specialist not found")
    return _learning_service.list_lessons(db, specialist_slug=slug, limit=limit)
