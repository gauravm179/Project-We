from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.core.config import get_settings
from app.db.models import ChatMessage
from app.memory.service import MemoryService
from app.schemas.chat import ChatHistoryItem, ChatReply

logger = logging.getLogger(__name__)


class BrainService:
    def __init__(self) -> None:
        self._memory_service = MemoryService()

    async def chat(self, db: Session, user_message: str) -> ChatReply:
        user_record = ChatMessage(role="user", content=user_message)
        db.add(user_record)
        db.flush()

        self._memory_service.extract_and_store(db=db, message=user_message)

        provider = build_provider(get_settings())
        assistant_text = await provider.generate(user_message)

        assistant_record = ChatMessage(role="assistant", content=assistant_text)
        db.add(assistant_record)
        db.commit()

        return ChatReply(response=assistant_text)

    def history(self, db: Session, limit: int = 50) -> list[ChatHistoryItem]:
        stmt = select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [
            ChatHistoryItem(role=row.role, content=row.content, created_at=row.created_at)
            for row in rows
        ]
