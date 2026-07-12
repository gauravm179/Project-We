from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/")
def root() -> dict[str, str]:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }
