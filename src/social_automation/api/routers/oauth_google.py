"""OAuth web Google Drive per Vercel."""

from __future__ import annotations

import json
import os
import secrets

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from social_automation.api.deps import SettingsDep
from social_automation.drive.auth import SCOPES

router = APIRouter(prefix="/oauth/google", tags=["oauth"])

_PENDING_STATES: dict[str, bool] = {}


def _redirect_uri(settings: SettingsDep) -> str:
    explicit = (settings.google_redirect_uri or "").strip()
    if explicit:
        return explicit
    vercel_url = (os.environ.get("VERCEL_URL") or "").strip()
    if vercel_url:
        return f"https://{vercel_url}/api/v1/oauth/google/callback"
    return "http://127.0.0.1:8000/api/v1/oauth/google/callback"


@router.get("/start")
def google_oauth_start(settings: SettingsDep):
    creds_raw = (settings.google_credentials_json or "").strip()
    if not creds_raw:
        raise HTTPException(400, detail="GOOGLE_CREDENTIALS_JSON non configurato")
    config = json.loads(creds_raw)
    flow = Flow.from_client_config(
        config,
        scopes=list(SCOPES),
        redirect_uri=_redirect_uri(settings),
    )
    state = secrets.token_urlsafe(16)
    _PENDING_STATES[state] = True
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    return RedirectResponse(auth_url)


@router.get("/callback")
def google_oauth_callback(code: str, state: str, settings: SettingsDep):
    if state not in _PENDING_STATES:
        raise HTTPException(400, detail="State OAuth non valido")
    _PENDING_STATES.pop(state, None)
    creds_raw = (settings.google_credentials_json or "").strip()
    config = json.loads(creds_raw)
    flow = Flow.from_client_config(
        config,
        scopes=list(SCOPES),
        redirect_uri=_redirect_uri(settings),
    )
    flow.fetch_token(code=code)
    refresh = flow.credentials.refresh_token or ""
    if not refresh:
        raise HTTPException(400, detail="Refresh token non ricevuto — ripeti con prompt=consent")
    return {
        "ok": True,
        "message": "Salva GOOGLE_REFRESH_TOKEN nelle env Vercel (Sensitive)",
        "refresh_token": refresh,
    }


@router.get("/status")
def google_oauth_status(settings: SettingsDep):
    return {
        "credentials_configured": bool((settings.google_credentials_json or "").strip()),
        "refresh_token_configured": bool((settings.google_refresh_token or "").strip()),
    }
