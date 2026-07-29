from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.web_learning import (
    WebAssistRequest,
    WebCaptureRequest,
    WebCaptureResponse,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResultItem,
)
from app.web_learning.service import CaptureResult, SearchPersistResult, WebLearningService

router = APIRouter(prefix="/web", tags=["web"])
_service = WebLearningService()
WEB_LEARNER_SLUG = "web-learner-bot"


@router.post("/search")
async def web_search(payload: WebSearchRequest, db: Session = Depends(get_db)):
    result = await _service.search_web(
        db,
        payload.query,
        engine=payload.engine,
        limit=payload.limit,
        auto_capture_top=payload.auto_capture_top,
    )
    if isinstance(result, dict):
        if result.get("requires_permission"):
            return result  # type: ignore[return-value]
        raise HTTPException(status_code=400, detail=str(result.get("error", "Search failed")))
    return _search_to_response(result)


@router.post("/capture")
async def web_capture(payload: WebCaptureRequest, db: Session = Depends(get_db)):
    result = await _service.capture_url(
        db,
        WEB_LEARNER_SLUG,
        str(payload.url),
        max_images=payload.max_images,
    )
    if isinstance(result, dict):
        if result.get("requires_permission"):
            return result  # type: ignore[return-value]
        raise HTTPException(status_code=400, detail=str(result.get("error", "Capture failed")))
    return _capture_to_response(result)


@router.post("/assist")
async def web_assist(payload: WebAssistRequest, db: Session = Depends(get_db)):
    """Shared web assist for any bot — search + capture via web-learner-bot."""
    result = await _service.assist_for_message(
        db,
        payload.message,
        requesting_bot=payload.requesting_bot,
    )
    if isinstance(result, dict):
        return result
    if result.requires_permission:
        return {
            "requires_permission": True,
            "required_capability": "internet",
            "permission_request_id": result.permission_request_id,
            "message": result.message,
            "delegated_to": WEB_LEARNER_SLUG,
        }
    return {
        "delegated_to": WEB_LEARNER_SLUG,
        "search_id": result.search_id,
        "capture_ids": list(result.capture_ids),
        "context": result.context,
    }


def _capture_to_response(result: CaptureResult) -> WebCaptureResponse:
    return WebCaptureResponse(
        capture_id=result.capture_id,
        url=result.url,
        title=result.title,
        text_chars=result.text_chars,
        image_count=result.image_count,
        compressed_bytes=result.compressed_bytes,
        summary=result.summary,
        message=f"Stored compressed learning at data/web_learning/captures/{result.capture_id}/",
    )


def _search_to_response(result: SearchPersistResult) -> WebSearchResponse:
    return WebSearchResponse(
        search_id=result.search_id,
        engine=result.engine,
        query=result.query,
        result_count=result.result_count,
        compressed_bytes=result.compressed_bytes,
        results=[
            WebSearchResultItem(title=r.title, url=r.url, snippet=r.snippet) for r in result.results
        ],
        message=f"Stored compressed search at data/web_learning/searches/{result.search_id}/",
    )
