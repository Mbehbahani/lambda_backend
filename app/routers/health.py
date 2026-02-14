"""
Health-check router.
"""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.ai import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app_version)
