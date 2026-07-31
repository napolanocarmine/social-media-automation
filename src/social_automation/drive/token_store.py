"""Risoluzione refresh token Google Drive (DB → env → token.json)."""

from __future__ import annotations

import json
from pathlib import Path

from social_automation.settings import Settings

GOOGLE_DRIVE_PROVIDER = "google_drive"


def resolve_google_refresh_token(
    settings: Settings,
    *,
    db_path: Path | None = None,
) -> str:
    path = db_path or settings.db_path
    try:
        from social_automation.db.store import get_oauth_refresh_token

        db_token = get_oauth_refresh_token(path, provider=GOOGLE_DRIVE_PROVIDER)
        if db_token:
            return db_token
    except Exception:
        pass

    env_token = (settings.google_refresh_token or "").strip()
    if env_token:
        return env_token

    token_path = settings.google_token_path
    if token_path.is_file():
        try:
            data = json.loads(token_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                file_token = str(data.get("refresh_token") or "").strip()
                if file_token:
                    return file_token
        except (ValueError, TypeError, OSError):
            pass
    return ""
