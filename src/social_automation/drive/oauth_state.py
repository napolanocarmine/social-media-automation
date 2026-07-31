"""State OAuth firmato (compatibile serverless Vercel) + PKCE."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from social_automation.settings import Settings

_MAX_AGE_SECONDS = 900


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _state_secret(settings: Settings) -> bytes:
    for candidate in (
        (settings.cron_secret or "").strip(),
        (settings.google_credentials_json or "")[:128],
    ):
        if candidate:
            return candidate.encode("utf-8")
    return b"story-oauth-state-dev"


def create_signed_oauth_state(
    settings: Settings,
    *,
    code_verifier: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "nonce": secrets.token_urlsafe(16),
        "ts": int(time.time()),
    }
    verifier = (code_verifier or "").strip()
    if verifier:
        payload["cv"] = verifier
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_state_secret(settings), raw, hashlib.sha256).hexdigest()
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{body}.{sig}"


def parse_signed_oauth_state(
    settings: Settings,
    state: str,
    *,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> dict[str, Any] | None:
    try:
        body, sig = (state or "").rsplit(".", 1)
        if not body or not sig:
            return None
        pad = "=" * (-len(body) % 4)
        raw = base64.urlsafe_b64decode(body + pad)
        expected = hmac.new(_state_secret(settings), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        ts = int(payload.get("ts") or 0)
        if int(time.time()) - ts > int(max_age_seconds):
            return None
        if not str(payload.get("nonce") or "").strip():
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def verify_signed_oauth_state(
    settings: Settings,
    state: str,
    *,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> bool:
    return parse_signed_oauth_state(
        settings,
        state,
        max_age_seconds=max_age_seconds,
    ) is not None
