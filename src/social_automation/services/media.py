"""Risoluzione sicura path/URL media per API."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from social_automation.db.store import (
    get_image_record,
    latest_metadata_for_image,
    update_image_media_paths,
)
from social_automation.services.project_paths import project_root
from social_automation.settings import Settings, load_settings, resolve_media_file_path
from social_automation.storage import get_storage


def _content_type_for_path(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def maybe_persist_processed_media_to_blob(
    db_path: Path,
    *,
    image_id: int,
    settings: Settings,
    processed_path: Path,
    source_path: Path | None = None,
    original_path: str | None = None,
    generated_image_path: str | None = None,
    source_asset_id: str | None = None,
    platform: str = "instagram",
) -> dict[str, str]:
    """Su Vercel Blob: upload file locali (/tmp) e salva URL in Postgres."""
    backend = (settings.storage_backend or "local").strip().lower()
    if backend not in {"vercel_blob", "blob"}:
        return {}
    if not processed_path.is_file():
        return {}

    storage = get_storage(settings)
    updates: dict[str, str] = {}
    platform_key = (platform or "instagram").strip().lower() or "instagram"

    processed_url = storage.upload(
        f"processed/{platform_key}/{image_id}.jpg",
        processed_path.read_bytes(),
        content_type=_content_type_for_path(processed_path),
    )
    updates["path"] = processed_url

    if source_path is not None and source_path.is_file():
        asset_key = (source_asset_id or str(image_id)).strip() or str(image_id)
        original_url = storage.upload(
            f"originals/drive/{asset_key}.jpg",
            source_path.read_bytes(),
            content_type=_content_type_for_path(source_path),
        )
        updates["original_path"] = original_url
    elif (original_path or "").strip():
        orig = Path(original_path.strip())
        if orig.is_file() and not storage.is_remote_url(original_path):
            original_url = storage.upload(
                f"originals/local/{image_id}.jpg",
                orig.read_bytes(),
                content_type=_content_type_for_path(orig),
            )
            updates["original_path"] = original_url

    gen_raw = (generated_image_path or "").strip()
    if gen_raw and not storage.is_remote_url(gen_raw):
        gen_path = Path(gen_raw)
        if gen_path.is_file() and gen_path.resolve() != processed_path.resolve():
            generated_url = storage.upload(
                f"processed/{platform_key}/{image_id}-generated.jpg",
                gen_path.read_bytes(),
                content_type=_content_type_for_path(gen_path),
            )
            updates["generated_image_path"] = generated_url

    if updates:
        update_image_media_paths(
            db_path,
            image_id=image_id,
            path=updates.get("path"),
            original_path=updates.get("original_path"),
            generated_image_path=updates.get("generated_image_path"),
        )
    return updates


def media_urls_for_image(image_id: int, row: dict[str, Any] | None = None) -> dict[str, str]:
    """URL per preview immagini — Blob diretto o proxy API locale."""
    if row:
        processed = str(row.get("path") or "").strip()
        original = str(row.get("original_path") or "").strip()
        storage = get_storage()
        if processed and storage.is_remote_url(processed):
            proc_url = processed
        else:
            proc_url = f"/api/v1/media/images/{image_id}/processed"
        if original and storage.is_remote_url(original):
            orig_url = original
        else:
            orig_url = f"/api/v1/media/images/{image_id}/original"
        return {"processed": proc_url, "original": orig_url}
    base = f"/api/v1/media/images/{image_id}"
    return {"processed": f"{base}/processed", "original": f"{base}/original"}


def _allowed_output_roots(settings: Settings | None = None) -> list[Path]:
    s = settings or load_settings()
    roots: list[Path] = []
    if s.output_dir:
        roots.append(s.output_dir.resolve())
    default = (project_root() / "output").resolve()
    if default not in roots:
        roots.append(default)
    return roots


def _is_under_allowed_root(path: Path, settings: Settings | None = None) -> bool:
    resolved = path.resolve()
    for root in _allowed_output_roots(settings):
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve_processed_url(
    db_path: Path,
    *,
    image_id: int,
    settings: Settings | None = None,
) -> str | None:
    row = get_image_record(db_path, image_id=image_id)
    if row is None:
        return None
    raw = str(row.get("path") or "").strip()
    if not raw:
        return None
    storage = get_storage(settings)
    if storage.is_remote_url(raw):
        return raw
    path = resolve_media_file_path(raw)
    if path is None or not _is_under_allowed_root(path, settings):
        return None
    return str(path)


def resolve_original_url(
    db_path: Path,
    *,
    image_id: int,
    row: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str | None:
    data = row if row is not None else get_image_record(db_path, image_id=image_id)
    if data is None:
        return None
    meta = latest_metadata_for_image(db_path, image_id=image_id)
    candidates = [
        str((meta or {}).get("source_file") or "").strip(),
        str(data.get("original_path") or "").strip(),
        str(data.get("path") or "").strip(),
    ]
    storage = get_storage(settings)
    for raw in candidates:
        if not raw:
            continue
        if storage.is_remote_url(raw):
            return raw
        path = resolve_media_file_path(raw)
        if path is not None and _is_under_allowed_root(path, settings):
            return str(path)
    return None


def resolve_processed_path(
    db_path: Path,
    *,
    image_id: int,
    settings: Settings | None = None,
) -> Path | None:
    url = resolve_processed_url(db_path, image_id=image_id, settings=settings)
    if url is None:
        return None
    if get_storage(settings).is_remote_url(url):
        return None
    path = Path(url)
    return path if path.is_file() else None


def resolve_original_path(
    db_path: Path,
    *,
    image_id: int,
    row: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> Path | None:
    url = resolve_original_url(db_path, image_id=image_id, row=row, settings=settings)
    if url is None:
        return None
    if get_storage(settings).is_remote_url(url):
        return None
    path = Path(url)
    return path if path.is_file() else None


def resolve_dispatch_image_path(
    image_path_raw: str,
    *,
    settings: Settings | None = None,
) -> Path:
    """Risolve path locale o scarica da Blob in /tmp per dispatch Meta."""
    raw = (image_path_raw or "").strip()
    if not raw:
        raise FileNotFoundError("Path immagine vuoto")
    storage = get_storage(settings)
    if storage.is_remote_url(raw):
        return storage.download_to_tmp(raw)
    path = Path(raw)
    if path.is_file():
        return path
    resolved = resolve_media_file_path(raw)
    if resolved is not None and resolved.is_file():
        return resolved
    raise FileNotFoundError(f"File render non trovato: {raw}")
