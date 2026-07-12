from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.brain.service import BrainService
from app.db.session import get_db
from app.schemas.chat import ChatHistoryItem, ChatReply, ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])
brain_service = BrainService()


@router.post("", response_model=ChatReply)
async def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatReply:
    return await brain_service.chat(db=db, user_message=request.message)


@router.get("/history", response_model=list[ChatHistoryItem])
def chat_history(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ChatHistoryItem]:
    return brain_service.history(db=db, limit=limit)
