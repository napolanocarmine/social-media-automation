from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.services.media import (
    resolve_original_url,
    resolve_processed_url,
)
from social_automation.storage import get_storage

router = APIRouter(prefix="/media/images", tags=["media"])


def _file_response(path) -> FileResponse:
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.get("/{image_id}/processed")
def serve_processed(
    image_id: int,
    settings: SettingsDep,
    db_path: DbPathDep,
):
    url = resolve_processed_url(db_path, image_id=image_id, settings=settings)
    if url is None:
        raise HTTPException(status_code=404, detail="File processato non trovato")
    if get_storage(settings).is_remote_url(url):
        return RedirectResponse(url, status_code=302)
    return _file_response(url)


@router.get("/{image_id}/original")
def serve_original(
    image_id: int,
    settings: SettingsDep,
    db_path: DbPathDep,
):
    url = resolve_original_url(db_path, image_id=image_id, settings=settings)
    if url is None:
        raise HTTPException(status_code=404, detail="File originale non trovato")
    if get_storage(settings).is_remote_url(url):
        return RedirectResponse(url, status_code=302)
    return _file_response(url)
