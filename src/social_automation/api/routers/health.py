from __future__ import annotations

from fastapi import APIRouter

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.dashboard import HealthResponse
from social_automation.db.store import ensure_db_schema

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep, db_path: DbPathDep) -> HealthResponse:
    db_ok = False
    try:
        ensure_db_schema(db_path)
        db_ok = True
    except Exception:
        db_ok = False
    return HealthResponse(db_ok=db_ok, db_backend=settings.db_backend)
