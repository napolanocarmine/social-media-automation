from __future__ import annotations

from fastapi import APIRouter

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.dashboard import HealthResponse
from social_automation.db.store import ensure_db_schema

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep, db_path: DbPathDep) -> HealthResponse:
    db_ok = False
    db_error: str | None = None
    try:
        ensure_db_schema(db_path)
        db_ok = True
    except Exception as exc:
        db_error = str(exc).strip() or exc.__class__.__name__

    blob_configured = False
    blob_auth_mode: str | None = None
    try:
        from social_automation.storage.blob_store import BlobStorage

        blob_configured = BlobStorage.is_configured(settings)
        if blob_configured:
            auth = BlobStorage(settings).auth
            blob_auth_mode = auth.kind
    except Exception:
        blob_configured = False

    return HealthResponse(
        db_ok=db_ok,
        db_backend=settings.db_backend,
        db_error=db_error,
        storage_backend=settings.storage_backend,
        blob_configured=blob_configured,
        blob_auth_mode=blob_auth_mode,
    )
