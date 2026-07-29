from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["notes"])

NOTES_PATH = Path(__file__).resolve().parents[4] / "docs" / "NOTES.md"


@router.get("/notes")
def get_agent_notes() -> dict[str, str]:
    markdown = NOTES_PATH.read_text(encoding="utf-8") if NOTES_PATH.exists() else ""
    return {
        "title": "Project We — Agent Notes",
        "source": "docs/NOTES.md",
        "markdown": markdown,
        "browser_ui": "/ui/notes.html",
    }


@router.get("/notes/raw", response_class=PlainTextResponse)
def get_agent_notes_raw() -> str:
    if not NOTES_PATH.exists():
        return "Notes file not found."
    return NOTES_PATH.read_text(encoding="utf-8")
