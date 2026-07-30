from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    chat,
    control,
    health,
    inputs,
    learnings,
    memory,
    notes,
    permissions,
    runtime,
    safety,
    skills,
    specialists,
    voice,
    web,
)
from app.bootstrap import bootstrap_all_bots
from app.core.config import DATA_DIR, get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.runtime.service import heartbeat_loop, reset_start_time
from app.safety.service import SafetyService


@asynccontextmanager
async def lifespan(_: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    configure_logging()
    Base.metadata.create_all(bind=get_engine())
    with get_session_factory()() as db:
        bootstrap_all_bots(db)
        SafetyService().ensure_initialized(db)
    reset_start_time()
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(get_session_factory(), interval_seconds=60.0)
    )
    if get_settings().voice_enabled:
        try:
            await voice.voice_assistant.start(get_settings())
        except RuntimeError:
            # Keep API up; voice can be started later after deps/mic are ready.
            pass
    yield
    await voice.voice_assistant.stop()
    heartbeat_task.cancel()


app = FastAPI(
    title="Project We",
    version="0.3.6",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_safety_service = SafetyService()


@app.middleware("http")
async def emergency_stop_guard(request: Request, call_next):
    path = request.url.path
    if request.method == "POST" and path.startswith("/voice/command"):
        # Visible even if the route never runs (middleware/DB issues).
        import logging

        logging.getLogger("app.voice.middleware").info(
            "MIDDLEWARE POST %s received", path
        )

    # Skip DB for static assets, health, and all voice endpoints (status polls + commands).
    if (
        path.startswith("/safety")
        or path.startswith("/ui")
        or path.startswith("/voice")
        or path in {"/health", "/favicon.ico"}
    ):
        return await call_next(request)

    db = get_session_factory()()
    try:
        if _safety_service.is_emergency_stop_active(db):
            return JSONResponse(
                status_code=423,
                content={
                    "detail": (
                        "Emergency stop is active. Use the red SOS option flow in the client to "
                        "keep the app shut down. Only safety status endpoints are available."
                    )
                },
            )
    except Exception:  # noqa: BLE001 - never block the app on SOS read failures
        pass
    finally:
        db.close()

    return await call_next(request)

app.include_router(health.router)
app.include_router(notes.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(learnings.router)
app.include_router(inputs.router)
app.include_router(permissions.router)
app.include_router(control.router)
app.include_router(safety.router)
app.include_router(specialists.router)
app.include_router(skills.router)
app.include_router(web.router)
app.include_router(voice.router)
app.include_router(runtime.router)

STATIC_DIR = Path(__file__).parent / "static"
CHAT_INDEX = STATIC_DIR / "index.html"


@app.get("/ui", include_in_schema=False)
def chat_ui_no_slash() -> RedirectResponse:
    return RedirectResponse(url="/ui/", status_code=307)


@app.get("/chat-ui", include_in_schema=False)
def chat_ui_alias() -> FileResponse:
    return FileResponse(CHAT_INDEX)


@app.get("/web-ui", include_in_schema=False)
def web_learner_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "web-learner.html")


@app.get("/voice-ui", include_in_schema=False)
def voice_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "voice.html")


app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort: never leave Voice UI with a blank HTTP 500 for /voice/command."""
    import logging

    logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/voice/command"):
        return JSONResponse(
            {
                "transcript": "",
                "reply": f"Unhandled server error ({type(exc).__name__}: {exc}). Please try again.",
                "requires_permission": False,
                "permission_request_id": None,
                "routed_to": "master",
                "route_reason": f"unhandled: {type(exc).__name__}",
            },
            status_code=200,
        )
    return JSONResponse({"detail": str(exc)}, status_code=500)

