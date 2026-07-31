from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.services.media import (
    blob_url_requires_proxy,
    is_remote_media_url,
    resolve_original_url,
    resolve_processed_url,
    serve_remote_media_bytes,
)

router = APIRouter(prefix="/media/images", tags=["media"])


def _file_response(path) -> FileResponse:
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


def _remote_media_response(url: str, settings: SettingsDep) -> Response | RedirectResponse:
    if blob_url_requires_proxy(url, settings):
        data, media_type = serve_remote_media_bytes(url, settings=settings)
        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )
    return RedirectResponse(url, status_code=302)


@router.get("/{image_id}/processed")
def serve_processed(
    image_id: int,
    settings: SettingsDep,
    db_path: DbPathDep,
):
    url = resolve_processed_url(db_path, image_id=image_id, settings=settings)
    if url is None:
        raise HTTPException(status_code=404, detail="File processato non trovato")
    if is_remote_media_url(url):
        return _remote_media_response(url, settings)
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
    if is_remote_media_url(url):
        return _remote_media_response(url, settings)
    return _file_response(url)
