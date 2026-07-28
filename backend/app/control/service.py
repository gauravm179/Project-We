from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.providers import build_provider
from app.core.config import get_settings
from app.db.models import ControlAction, ControlSession
from app.memory.service import MemoryService
from app.schemas.control import (
    AssistResponse,
    ControlActionRecord,
    ControlSessionRecord,
)


_WRITE_ACTION_TYPES = {
    "click",
    "type",
    "submit_form",
    "send_email",
    "replace_text",
}


class ControlService:
    def __init__(self) -> None:
        self._memory_service = MemoryService()

    def create_session(self, db: Session, *, shared: bool, purpose: str, allow_write: bool) -> ControlSessionRecord:
        if not shared:
            raise ValueError("Control session requires explicit shared=true consent.")

        row = ControlSession(
            purpose=purpose,
            status="active",
            allow_screen_read=True,
            allow_write=allow_write,
        )
        db.add(row)
        db.flush()
        return self._to_session_record(row)

    def list_sessions(self, db: Session, status: str | None = None) -> list[ControlSessionRecord]:
        stmt = select(ControlSession).order_by(ControlSession.id.desc())
        if status:
            stmt = stmt.where(ControlSession.status == status)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [self._to_session_record(row) for row in rows]

    def end_session(self, db: Session, session_id: int) -> ControlSessionRecord | None:
        row = db.get(ControlSession, session_id)
        if row is None:
            return None
        row.status = "ended"
        row.ended_at = datetime.now(timezone.utc)
        db.flush()
        return self._to_session_record(row)

    async def assist_with_screen_context(
        self,
        db: Session,
        *,
        session_id: int,
        task: str,
        instruction: str,
        screen_context: str,
    ) -> AssistResponse | None:
        session = db.get(ControlSession, session_id)
        if session is None or session.status != "active":
            return None

        # Save useful user intent from instruction/context into local memory.
        self._memory_service.extract_and_store(db=db, message=instruction)
        self._memory_service.extract_and_store(db=db, message=screen_context)

        provider = build_provider(get_settings())
        memory_context = self._memory_service.recent_context(db=db)
        prompt = self._build_assist_prompt(task=task, instruction=instruction, screen_context=screen_context)
        response = await provider.generate(prompt, memory_context=memory_context)

        return AssistResponse(
            session_id=session_id,
            task=task,
            response=response,
        )

    def create_action(
        self,
        db: Session,
        *,
        session_id: int,
        action_type: str,
        target: str,
        payload: str,
    ) -> ControlActionRecord | None:
        session = db.get(ControlSession, session_id)
        if session is None or session.status != "active":
            return None
        if action_type in _WRITE_ACTION_TYPES and not session.allow_write:
            raise PermissionError("This session does not allow write actions.")

        preview = f"{action_type} on {target}"
        if payload:
            preview += f" with payload: {payload[:120]}"

        row = ControlAction(
            session_id=session_id,
            action_type=action_type,
            target=target,
            payload=payload,
            status="pending",
            preview=preview,
        )
        db.add(row)
        db.flush()
        return self._to_action_record(row)

    def list_actions(self, db: Session, session_id: int | None = None) -> list[ControlActionRecord]:
        stmt = select(ControlAction).order_by(ControlAction.id.desc())
        if session_id is not None:
            stmt = stmt.where(ControlAction.session_id == session_id)
        rows = db.scalars(stmt).all()
        rows.reverse()
        return [self._to_action_record(row) for row in rows]

    def decide_action(self, db: Session, action_id: int, approve: bool) -> ControlActionRecord | None:
        row = db.get(ControlAction, action_id)
        if row is None:
            return None
        row.status = "approved" if approve else "rejected"
        row.resolved_at = datetime.now(timezone.utc)
        db.flush()
        return self._to_action_record(row)

    def execute_action(self, db: Session, action_id: int) -> ControlActionRecord | None:
        row = db.get(ControlAction, action_id)
        if row is None:
            return None
        if row.status != "approved":
            raise PermissionError("Only approved actions can be executed.")

        row.status = "executed"
        row.result = (
            "Execution recorded. Wire this to a local automation engine (Playwright/OS accessibility) "
            "for real mouse/keyboard control."
        )
        row.resolved_at = datetime.now(timezone.utc)
        db.flush()
        return self._to_action_record(row)

    def _build_assist_prompt(self, *, task: str, instruction: str, screen_context: str) -> str:
        if task == "email_draft":
            return (
                "You are a local assistant helping draft an email from shared on-screen context.\n"
                "Return a complete email draft with subject and body.\n\n"
                f"Instruction: {instruction}\n\n"
                f"Screen context:\n{screen_context}"
            )
        return (
            "You are a local assistant helping fill a form from shared on-screen context.\n"
            "Return concise field-value suggestions.\n\n"
            f"Instruction: {instruction}\n\n"
            f"Screen context:\n{screen_context}"
        )

    def _to_session_record(self, row: ControlSession) -> ControlSessionRecord:
        return ControlSessionRecord(
            id=row.id,
            purpose=row.purpose,
            status=row.status,
            allow_screen_read=row.allow_screen_read,
            allow_write=row.allow_write,
            created_at=row.created_at,
            ended_at=row.ended_at,
        )

    def _to_action_record(self, row: ControlAction) -> ControlActionRecord:
        return ControlActionRecord(
            id=row.id,
            session_id=row.session_id,
            action_type=row.action_type,
            target=row.target,
            payload=row.payload,
            status=row.status,
            preview=row.preview,
            result=row.result,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )

