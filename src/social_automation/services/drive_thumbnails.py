"""Anteprime Drive con cache locale (dev) o Vercel Blob (prod)."""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path

from social_automation.drive.client import DriveClient
from social_automation.processing.image_adjust import normalize_image_file
from social_automation.settings import Settings

_LOG = logging.getLogger(__name__)


def drive_cache_path(settings: Settings, file_id: str, mime_type: str) -> Path:
    ext = mimetypes.guess_extension(mime_type) or ".jpg"
    return settings.output_dir / "drive_cache" / "exif" / f"{file_id}{ext}"


def _blob_thumb_key(file_id: str, mime_type: str) -> str:
    ext = mimetypes.guess_extension(mime_type) or ".jpg"
    return f"thumbnails/drive/{file_id}{ext}"


def _use_blob_cache(settings: Settings) -> bool:
    backend = (settings.storage_backend or "local").strip().lower()
    return backend in {"vercel_blob", "blob"}


def _blob_cache_available(settings: Settings) -> bool:
    if not _use_blob_cache(settings):
        return False
    from social_automation.storage.blob_store import BlobStorage

    return BlobStorage.is_configured(settings)


def _download_from_drive(
    settings: Settings,
    *,
    file_id: str,
    mime_type: str,
    open_browser: bool,
) -> tuple[bytes, str] | None:
    mime = (mime_type or "image/jpeg").strip() or "image/jpeg"
    ext = mimetypes.guess_extension(mime) or ".jpg"
    drive_client = DriveClient.from_settings(settings, open_browser=open_browser)
    try:
        raw = drive_client.download_file_bytes(file_id)
        data = _normalize_bytes(raw, suffix=ext)
        return data, mime
    except Exception as exc:
        _LOG.warning("Download thumbnail Drive fallito (%s): %s", file_id, exc)
        return None


def _normalize_bytes(data: bytes, *, suffix: str) -> bytes:
    fd, name = tempfile.mkstemp(suffix=suffix)
    tmp = Path(name)
    try:
        os.close(fd)
        tmp.write_bytes(data)
        normalize_image_file(tmp)
        return tmp.read_bytes()
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def clear_drive_thumb_cache(settings: Settings) -> None:
    if _blob_cache_available(settings):
        return
    exif_dir = settings.output_dir / "drive_cache" / "exif"
    if not exif_dir.is_dir():
        return
    for entry in exif_dir.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def get_drive_thumbnail_bytes(
    settings: Settings,
    *,
    file_id: str,
    mime_type: str,
    open_browser: bool = False,
) -> tuple[bytes, str] | None:
    """Scarica anteprima Drive (con cache). Restituisce (bytes, content_type)."""
    mime = (mime_type or "image/jpeg").strip() or "image/jpeg"

    if _blob_cache_available(settings):
        from social_automation.storage.factory import get_storage

        try:
            storage = get_storage(settings)
        except Exception as exc:
            _LOG.warning("Blob storage non disponibile per thumbnail: %s", exc)
        else:
            key = _blob_thumb_key(file_id, mime)
            try:
                existing = storage.exists(key)
                if existing:
                    return storage.download(existing), mime
            except Exception as exc:
                _LOG.warning("Lettura cache blob thumbnail fallita (%s): %s", key, exc)

            result = _download_from_drive(
                settings,
                file_id=file_id,
                mime_type=mime,
                open_browser=open_browser,
            )
            if result is None:
                return None
            data, content_type = result
            try:
                storage.upload(key, data, content_type=content_type)
            except Exception as exc:
                _LOG.warning("Scrittura cache blob thumbnail fallita (%s): %s", key, exc)
            return data, content_type

    if _use_blob_cache(settings) and os.environ.get("VERCEL"):
        _LOG.info(
            "Blob non configurato su Vercel: anteprima servita da Drive senza cache (%s)",
            file_id,
        )
        return _download_from_drive(
            settings,
            file_id=file_id,
            mime_type=mime,
            open_browser=open_browser,
        )

    cache_path = drive_cache_path(settings, file_id, mime)
    if cache_path.is_file():
        return cache_path.read_bytes(), mime

    drive_client = DriveClient.from_settings(settings, open_browser=open_browser)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(drive_client.download_file_bytes(file_id))
        normalize_image_file(cache_path)
        return cache_path.read_bytes(), mime
    except Exception as exc:
        _LOG.warning("Cache locale thumbnail fallita (%s): %s", file_id, exc)
        return None


def get_drive_thumbnail(
    settings: Settings,
    *,
    file_id: str,
    mime_type: str,
    open_browser: bool = False,
) -> Path | None:
    """Compat: restituisce path solo per cache locale (dev)."""
    if _use_blob_cache(settings):
        result = get_drive_thumbnail_bytes(
            settings,
            file_id=file_id,
            mime_type=mime_type,
            open_browser=open_browser,
        )
        if result is None:
            return None
        data, _ = result
        fd, name = tempfile.mkstemp(suffix=mimetypes.guess_extension(mime_type) or ".jpg")
        tmp = Path(name)
        os.close(fd)
        tmp.write_bytes(data)
        return tmp
    cache_path = drive_cache_path(settings, file_id, mime_type)
    if cache_path.is_file():
        return cache_path
    result = get_drive_thumbnail_bytes(
        settings,
        file_id=file_id,
        mime_type=mime_type,
        open_browser=open_browser,
    )
    if result is None:
        return None
    return cache_path if cache_path.is_file() else None
