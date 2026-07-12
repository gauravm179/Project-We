from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, control, health, inputs, memory, permissions, safety
from app.core.config import DATA_DIR
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.safety.service import SafetyService


@asynccontextmanager
async def lifespan(_: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    configure_logging()
    Base.metadata.create_all(bind=get_engine())
    yield


app = FastAPI(
    title="Project We",
    version="0.2.0",
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
_session_factory = get_session_factory()


@app.middleware("http")
async def emergency_stop_guard(request: Request, call_next):
    if request.url.path.startswith("/safety"):
        return await call_next(request)

    db = _session_factory()
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
    finally:
        db.close()

    return await call_next(request)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(inputs.router)
app.include_router(permissions.router)
app.include_router(control.router)
app.include_router(safety.router)
