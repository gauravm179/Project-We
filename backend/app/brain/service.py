from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.brain.router import route_message
from app.core.config import get_settings
from app.db.models import ChatMessage
from app.learning.local_store import (
    LocalLearningStore,
    extract_explicit_learning,
    is_shared_learning_policy_ask,
    maybe_record_web_assist,
)
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
        self._local_learnings = LocalLearningStore()

    async def chat(self, db: Session, user_message: str) -> ChatReply:
        user_record = ChatMessage(role="user", content=user_message)
        db.add(user_record)
        db.flush()

        self._memory_service.extract_and_store(db=db, message=user_message)
        # Persist the user turn before model/web work so a later Ollama crash
        # (and voice rollback) cannot erase it from history.
        db.commit()

        if is_shared_learning_policy_ask(user_message):
            result = self._local_learnings.enable_for_all_bots(db)
            text = self._local_learnings.format_enable_reply(result)
            db.add(ChatMessage(role="assistant", content=text))
            db.commit()
            return ChatReply(
                response=text,
                routed_to="master",
                route_reason="shared local learning enabled",
            )

        explicit = extract_explicit_learning(user_message)
        if explicit:
            self._local_learnings.record(
                db,
                bot_slug="master",
                kind="insight",
                title="User note",
                content=explicit,
                source_ref="explicit-remember",
                shared=True,
            )

        permission_reply = self._policy_service.parse_permission_reply(user_message)
        if permission_reply is not None:
            from app.progress import progress

            progress.step(
                "permission",
                ("Approve" if permission_reply else "Reject") + " internet from chat",
            )
            return await self._handle_permission_reply(
                db, user_message=user_message, approve=permission_reply
            )

        return await self._process_user_message(db, user_message)

    async def _handle_permission_reply(
        self,
        db: Session,
        *,
        user_message: str,
        approve: bool,
    ) -> ChatReply:
        pending = self._policy_service.latest_pending(db, "internet")

        if not approve:
            rejected = self._policy_service.reject_all_pending(db, "internet")
            if not rejected and not pending:
                text = "There is no pending internet request to deny."
            else:
                text = "Okay — internet access denied. I will stay local-only."
            db.add(ChatMessage(role="assistant", content=text))
            db.commit()
            return ChatReply(
                response=text,
                routed_to="master",
                route_reason="permission rejected by chat",
            )

        # Approve
        approved = self._policy_service.approve_all_pending(db, "internet")
        retry_message = None
        if approved:
            # Only retry the ask tied to the permission we just granted — never an older chart ask.
            retry_message = self._policy_service.message_from_permission_reason(
                approved[-1].reason
            )

        if not approved and self._policy_service.has_approved_capability(db, "internet"):
            # Already approved — do not dig up unrelated older web asks from history.
            text = (
                "Internet access is already approved. "
                "Ask your question again (e.g. “show me current affairs” or paste a URL)."
            )
            db.add(ChatMessage(role="assistant", content=text))
            db.commit()
            return ChatReply(
                response=text,
                routed_to="master",
                route_reason="internet already approved — ask again",
            )

        if not approved:
            text = (
                "I did not find a pending internet request. "
                "Ask again with a URL or ‘search for …’ / ‘current affairs’, then say yes to approve."
            )
            db.add(ChatMessage(role="assistant", content=text))
            db.commit()
            return ChatReply(
                response=text,
                routed_to="master",
                route_reason="no pending permission",
            )

        if not retry_message:
            text = (
                "Internet access approved. "
                "Send your URL or question again and I will continue."
            )
            db.add(ChatMessage(role="assistant", content=text))
            db.commit()
            return ChatReply(
                response=text,
                routed_to="master",
                route_reason="permission approved, no retry message",
            )

        note = "Internet access approved. Continuing with your earlier request…"
        db.add(ChatMessage(role="assistant", content=note))
        db.flush()
        logger.info("Retrying after internet approval: %s", retry_message[:120])
        reply = await self._process_user_message(db, retry_message)
        # Prefix so the voice UI makes the approval clear.
        if not reply.response.startswith("Internet access approved"):
            reply = ChatReply(
                response=f"{note}\n\n{reply.response}",
                requires_permission=reply.requires_permission,
                required_capability=reply.required_capability,
                permission_request_id=reply.permission_request_id,
                routed_to=reply.routed_to,
                route_reason=f"approved then: {reply.route_reason}",
            )
        return reply

    def _find_retry_message_from_history(self, db: Session) -> str | None:
        """Prefer the most recent user ask that needs the web (skip yes/no replies)."""
        rows = db.scalars(
            select(ChatMessage).order_by(ChatMessage.id.desc()).limit(30)
        ).all()
        for row in rows:
            if row.role != "user":
                continue
            if self._policy_service.parse_permission_reply(row.content) is not None:
                continue
            if message_needs_web_assist(row.content) or self._policy_service.message_likely_needs_internet(
                row.content
            ):
                return row.content
        return None

    async def _process_user_message(self, db: Session, user_message: str) -> ChatReply:
        from app.progress import progress

        settings = get_settings()

        decision = route_message(user_message)
        progress.step("route", f"target={decision.target} ({decision.reason})")
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

            # If already approved, continue (do not ask again).
            if not self._policy_service.has_approved_capability(db, "internet"):
                request = self._policy_service.create_permission_request(
                    db=db,
                    capability="internet",
                    reason=f"Need live internet data for: {user_message}",
                )
                assistant_text = (
                    "This request likely needs live internet data. "
                    "Please approve internet access to continue "
                    "(reply yes / approved, or use the Approve button)."
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
        stored = self._local_learnings.recall_context(db, "master", limit=8)
        if stored:
            memory_context = (
                f"{memory_context}\n\n--- STORED LOCAL LEARNINGS ---\n{stored}"
                if memory_context
                else f"--- STORED LOCAL LEARNINGS ---\n{stored}"
            )

        if message_needs_web_assist(user_message):
            assist = await self._web_learning.assist_for_message(
                db, user_message, requesting_bot="master-bot"
            )
            if isinstance(assist, WebAssistResult) and assist.requires_permission:
                assistant_text = str(
                    assist.message
                    or "Internet permission required for web search or page reading. "
                    "Reply yes / approved to allow it."
                )
                if "Reply yes" not in assistant_text and "Approve" in assistant_text:
                    assistant_text = (
                        f"{assistant_text} Reply yes / approved to allow it."
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
                assistant_text = str(
                    assist.get(
                        "message",
                        "Internet permission required. Reply yes / approved to allow it.",
                    )
                )
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
                maybe_record_web_assist(
                    db,
                    bot_slug="master",
                    user_message=user_message,
                    context=assist.context,
                    capture_ids=list(assist.capture_ids or []),
                )

        assistant_text = await provider.generate(
            user_message,
            memory_context=memory_context,
            specialist_slug=None,
        )
        from app.progress import progress

        progress.step("model-done", f"master reply chars={len(assistant_text)}")

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
        from app.progress import progress

        progress.step("specialist", f"Delegating to {slug}")
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
        if specialist_reply.requires_permission and "Reply yes" not in response:
            response = f"{response} Reply yes / approved to allow it."

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
