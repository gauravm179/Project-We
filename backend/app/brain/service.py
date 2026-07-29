from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.brain.router import route_message
from app.core.config import get_settings
from app.db.models import ChatMessage
from app.memory.service import MemoryService
from app.policy.service import PolicyService
from app.schemas.chat import ChatHistoryItem, ChatReply
from app.specialists.service import SpecialistService
from app.web_learning.intent import message_needs_web_assist
from app.web_learning.service import WebAssistResult, WebLearningService

logger = logging.getLogger(__name__)


class BrainService:
    def __init__(self) -> None:
        self._memory_service = MemoryService()
        self._policy_service = PolicyService()
        self._web_learning = WebLearningService()
        self._specialists = SpecialistService()

    async def chat(self, db: Session, user_message: str) -> ChatReply:
        settings = get_settings()

        user_record = ChatMessage(role="user", content=user_message)
        db.add(user_record)
        db.flush()

        self._memory_service.extract_and_store(db=db, message=user_message)

        decision = route_message(user_message)
        if decision.target != "master":
            return await self._delegate_to_specialist(
                db, user_message=user_message, slug=decision.target, reason=decision.reason
            )

        needs_internet = self._policy_service.message_likely_needs_internet(user_message)
        if settings.strict_local_mode and needs_internet and settings.internet_mode in {"ask", "never"}:
            if settings.internet_mode == "never":
                assistant_text = (
                    "This request likely needs live internet data, but internet mode is set to NEVER. "
                    "Update settings if you want online help."
                )
                assistant_record = ChatMessage(role="assistant", content=assistant_text)
                db.add(assistant_record)
                db.commit()
                return ChatReply(
                    response=assistant_text,
                    requires_permission=False,
                    required_capability="internet",
                    routed_to="master",
                    route_reason=decision.reason,
                )

            request = self._policy_service.create_permission_request(
                db=db,
                capability="internet",
                reason=f"Need live internet data for: {user_message}",
            )
            assistant_text = (
                "This request likely needs live internet data. "
                "Please approve internet access to continue."
            )
            assistant_record = ChatMessage(role="assistant", content=assistant_text)
            db.add(assistant_record)
            db.commit()
            return ChatReply(
                response=assistant_text,
                requires_permission=True,
                required_capability="internet",
                permission_request_id=request.id,
                routed_to="master",
                route_reason=decision.reason,
            )

        provider = build_provider(settings)
        memory_context = self._memory_service.recent_context(db=db)

        if message_needs_web_assist(user_message):
            assist = await self._web_learning.assist_for_message(
                db, user_message, requesting_bot="master-bot"
            )
            if isinstance(assist, WebAssistResult) and assist.requires_permission:
                assistant_text = str(
                    assist.message or "Internet permission required for web search or page reading."
                )
                db.add(ChatMessage(role="assistant", content=assistant_text))
                db.commit()
                return ChatReply(
                    response=assistant_text,
                    requires_permission=True,
                    required_capability="internet",
                    permission_request_id=int(assist.permission_request_id),  # type: ignore[arg-type]
                    routed_to="master",
                    route_reason=decision.reason,
                )
            if isinstance(assist, dict) and assist.get("requires_permission"):
                assistant_text = str(assist.get("message", "Internet permission required."))
                db.add(ChatMessage(role="assistant", content=assistant_text))
                db.commit()
                return ChatReply(
                    response=assistant_text,
                    requires_permission=True,
                    required_capability="internet",
                    permission_request_id=int(assist["permission_request_id"]),  # type: ignore[arg-type]
                    routed_to="master",
                    route_reason=decision.reason,
                )
            if isinstance(assist, WebAssistResult) and assist.context:
                memory_context = (
                    f"{memory_context}\n\n--- WEB LEARNER ASSIST ---\n{assist.context}"
                    if memory_context
                    else f"--- WEB LEARNER ASSIST ---\n{assist.context}"
                )

        assistant_text = await provider.generate(user_message, memory_context=memory_context)

        assistant_record = ChatMessage(role="assistant", content=assistant_text)
        db.add(assistant_record)
        db.commit()

        return ChatReply(
            response=assistant_text,
            routed_to="master",
            route_reason=decision.reason,
        )

    async def _delegate_to_specialist(
        self,
        db: Session,
        *,
        user_message: str,
        slug: str,
        reason: str,
    ) -> ChatReply:
        logger.info("Master routing to %s (%s)", slug, reason)
        specialist_reply = await self._specialists.chat(db, slug, user_message)
        if specialist_reply is None:
            fallback = (
                f"I wanted to use {slug}, but that specialist is unavailable. "
                "Answering as the master bot instead."
            )
            db.add(ChatMessage(role="assistant", content=fallback))
            db.commit()
            return ChatReply(
                response=fallback,
                routed_to="master",
                route_reason=f"fallback from missing {slug}",
            )

        prefix = f"[via {specialist_reply.specialist_name}] "
        response = specialist_reply.response
        if not response.startswith("["):
            response = prefix + response

        db.add(ChatMessage(role="assistant", content=response))
        db.commit()
        return ChatReply(
            response=response,
            requires_permission=specialist_reply.requires_permission,
            required_capability=specialist_reply.required_capability,
            permission_request_id=specialist_reply.permission_request_id,
            routed_to=specialist_reply.specialist_slug,
            route_reason=reason,
        )

    def history(self, db: Session, limit: int = 50) -> list[ChatHistoryItem]:
        stmt = select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [
            ChatHistoryItem(role=row.role, content=row.content, created_at=row.created_at)
            for row in rows
        ]
