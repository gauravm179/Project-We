from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    chat,
    control,
    health,
    inputs,
    memory,
    permissions,
    runtime,
    safety,
    search,
    skills,
    specialists,
)
from app.core.config import DATA_DIR
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.runtime.service import heartbeat_loop, reset_start_time
from app.safety.service import SafetyService

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    configure_logging()
    Base.metadata.create_all(bind=get_engine())
    reset_start_time()
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(get_session_factory(), interval_seconds=60.0)
    )
    yield
    heartbeat_task.cancel()


app = FastAPI(
    title="Project We",
    version="0.3.0",
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
    if request.url.path.startswith("/safety"):
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
app.include_router(search.router)
app.include_router(specialists.router)
app.include_router(skills.router)
app.include_router(runtime.router)

app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
