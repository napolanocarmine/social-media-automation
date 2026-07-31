"""OAuth web Google Drive per Vercel e UI riconnessione."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.db.store import upsert_oauth_token
from social_automation.drive.auth import SCOPES, get_credentials_from_env
from social_automation.drive.oauth_redirect import resolve_google_oauth_redirect_uri
from social_automation.drive.oauth_state import (
    create_signed_oauth_state,
    generate_code_challenge,
    generate_code_verifier,
    parse_signed_oauth_state,
)
from social_automation.drive.token_store import GOOGLE_DRIVE_PROVIDER, resolve_google_refresh_token

router = APIRouter(prefix="/oauth/google", tags=["oauth"])

_OAUTH_SUCCESS_PATH = "/workflow/select?google=connected"


def _oauth_client_config(settings: SettingsDep) -> dict:
    creds_raw = (settings.google_credentials_json or "").strip()
    if not creds_raw:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "google_oauth_not_configured",
                "message": "GOOGLE_CREDENTIALS_JSON non configurato sul server.",
            },
        )
    return json.loads(creds_raw)


def _probe_google_token(settings: SettingsDep, db_path: DbPathDep) -> bool | None:
    creds_raw = (settings.google_credentials_json or "").strip()
    refresh = resolve_google_refresh_token(settings, db_path=db_path)
    if not creds_raw or not refresh:
        return None
    try:
        get_credentials_from_env(credentials_json=creds_raw, refresh_token=refresh)
        return True
    except Exception:
        return False


@router.get("/start")
def google_oauth_start(settings: SettingsDep, request: Request):
    config = _oauth_client_config(settings)
    redirect_uri = resolve_google_oauth_redirect_uri(settings, request=request)
    flow = Flow.from_client_config(
        config,
        scopes=list(SCOPES),
        redirect_uri=redirect_uri,
    )
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = create_signed_oauth_state(settings, code_verifier=code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
def google_oauth_callback(
    code: str,
    state: str,
    settings: SettingsDep,
    db_path: DbPathDep,
    request: Request,
):
    payload = parse_signed_oauth_state(settings, state)
    if payload is None:
        raise HTTPException(status_code=400, detail="State OAuth non valido o scaduto")
    code_verifier = str(payload.get("cv") or "").strip()
    if not code_verifier:
        raise HTTPException(status_code=400, detail="PKCE code_verifier mancante — riprova da /start")
    config = _oauth_client_config(settings)
    redirect_uri = resolve_google_oauth_redirect_uri(settings, request=request)
    flow = Flow.from_client_config(
        config,
        scopes=list(SCOPES),
        redirect_uri=redirect_uri,
    )
    try:
        flow.fetch_token(code=code, code_verifier=code_verifier)
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(status_code=400, detail=msg) from exc
    refresh = flow.credentials.refresh_token or ""
    if not refresh:
        raise HTTPException(
            status_code=400,
            detail="Refresh token non ricevuto — ripeti autorizzazione (prompt=consent)",
        )
    scopes = ",".join(flow.credentials.scopes or list(SCOPES))
    upsert_oauth_token(
        db_path,
        provider=GOOGLE_DRIVE_PROVIDER,
        refresh_token=refresh,
        scopes=scopes,
    )
    return RedirectResponse(_OAUTH_SUCCESS_PATH, status_code=302)


@router.get("/status")
def google_oauth_status(settings: SettingsDep, db_path: DbPathDep, request: Request):
    creds_configured = bool((settings.google_credentials_json or "").strip())
    refresh_configured = bool(resolve_google_refresh_token(settings, db_path=db_path))
    token_valid = _probe_google_token(settings, db_path) if creds_configured else None
    redirect_uri = resolve_google_oauth_redirect_uri(settings, request=request)
    return {
        "credentials_configured": creds_configured,
        "refresh_token_configured": refresh_configured,
        "token_valid": token_valid,
        "reconnect_url": "/api/v1/oauth/google/start",
        "redirect_uri": redirect_uri,
        "redirect_uri_source": _redirect_uri_source(settings, request),
        "token_source": _token_source(settings, db_path),
    }


def _redirect_uri_source(settings: SettingsDep, request: Request) -> str:
    if (settings.google_redirect_uri or "").strip():
        return "env"
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
    if host and host not in {"localhost", "127.0.0.1"}:
        return "request_host"
    if (os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip():
        return "vercel_production_url"
    if (os.environ.get("VERCEL_URL") or "").strip():
        return "vercel_url"
    return "localhost"


def _token_source(settings: SettingsDep, db_path: DbPathDep) -> str | None:
    from social_automation.db.store import get_oauth_refresh_token

    if get_oauth_refresh_token(db_path, provider=GOOGLE_DRIVE_PROVIDER):
        return "database"
    if (settings.google_refresh_token or "").strip():
        return "env"
    if settings.google_token_path.is_file():
        return "file"
    return None
