from __future__ import annotations

from fastapi import APIRouter

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.dashboard import HealthResponse
from social_automation.db.store import ensure_db_schema
from social_automation.drive.token_store import resolve_google_refresh_token

API_FEATURES = "google-drive-reconnect-2026-07-31"

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
    blob_store_id_present: bool | None = None
    blob_read_write_token_present: bool | None = None
    blob_oidc_token_present: bool | None = None
    blob_error: str | None = None
    try:
        from social_automation.storage.blob_store import blob_auth_diagnostics

        blob_diag = blob_auth_diagnostics(settings)
        blob_configured = bool(blob_diag["configured"])
        blob_auth_mode = blob_diag["auth_mode"]  # type: ignore[assignment]
        blob_store_id_present = bool(blob_diag["store_id_present"])
        blob_read_write_token_present = bool(blob_diag["read_write_token_present"])
        blob_oidc_token_present = bool(blob_diag["oidc_token_present"])
        blob_error = blob_diag["error"]  # type: ignore[assignment]
    except Exception as exc:
        blob_configured = False
        blob_error = str(exc).strip() or exc.__class__.__name__

    return HealthResponse(
        api_features=API_FEATURES,
        db_ok=db_ok,
        db_backend=settings.db_backend,
        db_error=db_error,
        storage_backend=settings.storage_backend,
        blob_configured=blob_configured,
        blob_auth_mode=blob_auth_mode,
        blob_store_id_present=blob_store_id_present,
        blob_read_write_token_present=blob_read_write_token_present,
        blob_oidc_token_present=blob_oidc_token_present,
        blob_error=blob_error,
        google_oauth_web_configured=bool((settings.google_credentials_json or "").strip()),
        google_refresh_configured=bool(
            resolve_google_refresh_token(settings, db_path=db_path)
        ),
    )
