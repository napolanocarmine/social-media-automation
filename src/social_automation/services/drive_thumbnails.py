"""Anteprime Drive con cache locale."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from social_automation.drive.client import DriveClient
from social_automation.processing.image_adjust import normalize_image_file
from social_automation.settings import Settings


def drive_cache_path(settings: Settings, file_id: str, mime_type: str) -> Path:
    ext = mimetypes.guess_extension(mime_type) or ".jpg"
    return settings.output_dir / "drive_cache" / "exif" / f"{file_id}{ext}"


def clear_drive_thumb_cache(settings: Settings) -> None:
    exif_dir = settings.output_dir / "drive_cache" / "exif"
    if not exif_dir.is_dir():
        return
    for entry in exif_dir.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def get_drive_thumbnail(
    settings: Settings,
    *,
    file_id: str,
    mime_type: str,
    open_browser: bool = False,
) -> Path | None:
    cache_path = drive_cache_path(settings, file_id, mime_type)
    if cache_path.is_file():
        return cache_path
    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive_client = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=open_browser,
        oauth_browser=oauth_browser,
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(drive_client.download_file_bytes(file_id))
        normalize_image_file(cache_path)
        return cache_path
    except Exception:
        return None
