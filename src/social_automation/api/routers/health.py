from __future__ import annotations

from fastapi import APIRouter

from social_automation.api.schemas.dashboard import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
