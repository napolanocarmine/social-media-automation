"""Risoluzione redirect URI OAuth Google (evita redirect_uri_mismatch)."""

from __future__ import annotations

import os

from starlette.requests import Request

from social_automation.settings import Settings

_CALLBACK_PATH = "/api/v1/oauth/google/callback"


def resolve_google_oauth_redirect_uri(
    settings: Settings,
    *,
    request: Request | None = None,
) -> str:
    """
    URI callback OAuth Google.

    Priorità:
    1. ``GOOGLE_REDIRECT_URI`` esplicito
    2. Host della richiesta HTTP (dominio con cui l'utente apre l'app)
    3. ``VERCEL_PROJECT_PRODUCTION_URL`` / ``VERCEL_URL``
    4. localhost dev
    """
    explicit = (settings.google_redirect_uri or "").strip()
    if explicit:
        return explicit.rstrip("/")

    if request is not None:
        host = (
            request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        ).split(",")[0].strip()
        if host and not host.startswith("127.0.0.1") and host != "localhost":
            proto = (request.headers.get("x-forwarded-proto") or "https").split(",")[0].strip()
            if proto not in {"http", "https"}:
                proto = "https"
            return f"{proto}://{host}{_CALLBACK_PATH}"

    for env_key in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            continue
        base = raw if raw.startswith("http") else f"https://{raw}"
        return f"{base.rstrip('/')}{_CALLBACK_PATH}"

    return f"http://127.0.0.1:8000{_CALLBACK_PATH}"
