from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.policy.service import PolicyService
from app.schemas.search import SearchRequest, SearchResponse, SearchResultRecord
from app.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])
_search_service = SearchService()
_policy_service = PolicyService()


@router.post("", response_model=SearchResponse)
async def web_search(request: SearchRequest, db: Session = Depends(get_db)):
    settings = get_settings()

    if settings.strict_local_mode and settings.internet_mode == "never":
        raise HTTPException(
            status_code=403,
            detail="Internet access is disabled. Set internet_mode to 'ask' or 'always'.",
        )

    if settings.strict_local_mode and settings.internet_mode == "ask":
        pending = _policy_service.list_permission_requests(db=db, status="approved")
        if not pending:
            perm = _policy_service.create_permission_request(
                db=db,
                capability="internet",
                reason=f"Web search: {request.query}",
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail=f"Internet permission required. Approve permission ID {perm.id} first.",
            )

    results = await _search_service.search(request.query, max_results=request.max_results)

    provider = "searxng" if settings.searxng_base_url else "duckduckgo"

    return SearchResponse(
        query=request.query,
        provider=provider,
        results=[
            SearchResultRecord(title=r.title, url=r.url, snippet=r.snippet)
            for r in results
        ],
        count=len(results),
    )
