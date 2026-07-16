from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from social_automation.api.deps import SettingsDep
from social_automation.api.schemas.drive_batches import (
    DriveAssetListResponse,
    DriveAssetSummary,
)
from social_automation.services.batch_runner import serialize_drive_asset
from social_automation.services.drive_selection import (
    load_drive_assets_for_selection,
)
from social_automation.services.drive_thumbnails import get_drive_thumbnail

DRIVE_PAGE_SIZE_DEFAULT = 12

router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/assets", response_model=DriveAssetListResponse)
def list_drive_assets(
    settings: SettingsDep,
    category: str = Query(..., min_length=1),
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=DRIVE_PAGE_SIZE_DEFAULT, ge=1, le=500),
    refresh_cache: bool = Query(default=False),
) -> DriveAssetListResponse:
    if refresh_cache:
        from social_automation.services.drive_thumbnails import clear_drive_thumb_cache

        clear_drive_thumb_cache(settings)
    try:
        assets = load_drive_assets_for_selection(
            settings,
            category=category.strip(),
            target_year=year,
            target_month=month,
            open_browser=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = len(assets)
    page_size = max(1, min(100, int(page_size)))
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 0
    page = min(max(0, int(page)), max(0, total_pages - 1)) if total else 0
    start = page * page_size
    page_assets = assets[start : start + page_size]
    return DriveAssetListResponse(
        items=[DriveAssetSummary(**serialize_drive_asset(a)) for a in page_assets],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/thumbnails/{file_id}")
def drive_thumbnail(
    file_id: str,
    settings: SettingsDep,
    mime_type: str = Query(default="image/jpeg"),
) -> FileResponse:
    path = get_drive_thumbnail(settings, file_id=file_id, mime_type=mime_type, open_browser=False)
    if path is None:
        raise HTTPException(status_code=404, detail="Anteprima non disponibile")
    return FileResponse(path)
