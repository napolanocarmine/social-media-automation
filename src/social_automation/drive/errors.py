"""Errori Google Drive → risposte HTTP strutturate."""

from __future__ import annotations

from fastapi import HTTPException
from google.auth.exceptions import RefreshError

_GOOGLE_RECONNECT_MESSAGE = (
    "Connessione Google Drive scaduta o revocata. "
    "Clicca «Riconnetti Google Drive» per autorizzare di nuovo l'account."
)


def is_google_token_error(exc: BaseException) -> bool:
    if isinstance(exc, RefreshError):
        return True
    msg = str(exc).lower()
    return "invalid_grant" in msg or "token has been expired or revoked" in msg


def http_error_from_google_auth(exc: BaseException) -> HTTPException | None:
    if not is_google_token_error(exc):
        return None
    return HTTPException(
        status_code=401,
        detail={
            "code": "google_token_expired",
            "message": _GOOGLE_RECONNECT_MESSAGE,
        },
    )
