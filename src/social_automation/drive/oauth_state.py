"""State OAuth firmato (compatibile serverless Vercel)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from social_automation.settings import Settings

_MAX_AGE_SECONDS = 900


def _state_secret(settings: Settings) -> bytes:
    for candidate in (
        (settings.cron_secret or "").strip(),
        (settings.google_credentials_json or "")[:128],
    ):
        if candidate:
            return candidate.encode("utf-8")
    return b"story-oauth-state-dev"


def create_signed_oauth_state(settings: Settings) -> str:
    payload = {"nonce": secrets.token_urlsafe(16), "ts": int(time.time())}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_state_secret(settings), raw, hashlib.sha256).hexdigest()
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{body}.{sig}"


def verify_signed_oauth_state(
    settings: Settings,
    state: str,
    *,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> bool:
    try:
        body, sig = (state or "").rsplit(".", 1)
        if not body or not sig:
            return False
        pad = "=" * (-len(body) % 4)
        raw = base64.urlsafe_b64decode(body + pad)
        expected = hmac.new(_state_secret(settings), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False
        payload = json.loads(raw.decode("utf-8"))
        ts = int(payload.get("ts") or 0)
        if int(time.time()) - ts > int(max_age_seconds):
            return False
        return bool(str(payload.get("nonce") or "").strip())
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
