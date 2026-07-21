"""OAuth2 per Google Drive API (desktop + web/Vercel)."""

from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)


def _browser_opener_for(name: str):
    """Restituisce una funzione compatibile con webbrowser.open(url, new=..., autoraise=...)."""
    key = name.strip().lower()

    def opener(url: str, new: int = 0, autoraise: bool = True) -> bool:
        if sys.platform == "darwin" and key == "safari":
            subprocess.run(["open", "-a", "Safari", url], check=False)
            return True
        try:
            return webbrowser.get(name).open(url, new=new, autoraise=autoraise)
        except webbrowser.Error:
            return webbrowser.open(url, new=new, autoraise=autoraise)

    return opener


def _run_local_server_opening_with(
    flow: InstalledAppFlow,
    *,
    browser: str,
    port: int = 0,
) -> Credentials:
    """Esegue run_local_server aprendo l'URL nel browser indicato (es. Safari su macOS)."""
    real_open = webbrowser.open
    webbrowser.open = _browser_opener_for(browser)  # type: ignore[method-assign]
    try:
        return flow.run_local_server(port=port)
    finally:
        webbrowser.open = real_open


def get_credentials(
    credentials_path: Path,
    token_path: Path,
    *,
    open_browser: bool = True,
    oauth_browser: str | None = None,
) -> Credentials:
    """Carica o crea credenziali utente; salva/aggiorna token su disco."""
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), list(SCOPES))

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except RefreshError:
            if token_path.is_file():
                token_path.unlink()
            creds = None
    if not creds or not creds.valid:
        if not credentials_path.is_file():
            msg = (
                f"File credenziali mancante: {credentials_path}. "
                "Scarica il JSON OAuth client (tipo Desktop) da Google Cloud Console."
            )
            raise FileNotFoundError(msg)
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), list(SCOPES))
        if open_browser:
            if oauth_browser and oauth_browser.strip():
                creds = _run_local_server_opening_with(
                    flow,
                    browser=oauth_browser.strip(),
                    port=0,
                )
            else:
                creds = flow.run_local_server(port=0)
        else:
            creds = flow.run_console()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_credentials_from_env(
    *,
    credentials_json: str,
    refresh_token: str,
) -> Credentials:
    """Credenziali Google da env vars (deploy Vercel)."""
    raw = (credentials_json or "").strip()
    if not raw:
        raise FileNotFoundError("GOOGLE_CREDENTIALS_JSON mancante")
    config = json.loads(raw)
    token = (refresh_token or "").strip()
    if not token:
        raise FileNotFoundError("GOOGLE_REFRESH_TOKEN mancante — esegui OAuth web")
    creds = Credentials(
        token=None,
        refresh_token=token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.get("installed", config.get("web", {})).get("client_id"),
        client_secret=config.get("installed", config.get("web", {})).get("client_secret"),
        scopes=list(SCOPES),
    )
    creds.refresh(Request())
    return creds


def build_drive_service(
    credentials_path: Path,
    token_path: Path,
    *,
    open_browser: bool = True,
    oauth_browser: str | None = None,
    credentials_json: str | None = None,
    refresh_token: str | None = None,
) -> Any:
    if (credentials_json or "").strip() and (refresh_token or "").strip():
        creds = get_credentials_from_env(
            credentials_json=str(credentials_json),
            refresh_token=str(refresh_token),
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    creds = get_credentials(
        credentials_path,
        token_path,
        open_browser=open_browser,
        oauth_browser=oauth_browser,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)
