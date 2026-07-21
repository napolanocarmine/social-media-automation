from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.drive_batches import (
    BatchDetailResponse,
    BatchStopRequest,
    BatchStopResponse,
    BatchSummary,
    StartAiBatchRequest,
    StartAiBatchResponse,
)
from social_automation.models import MediaFormat, Platform
from social_automation.services.batch_queue import process_batch_queue
from social_automation.services.batch_runner import start_selected_ai_batch
from social_automation.services.batches import (
    get_active_running_batch,
    get_batch_detail,
    list_batches_filtered,
    stop_batch,
)
from social_automation.services.drive_thumbnails import clear_drive_thumb_cache

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("", response_model=list[BatchSummary])
def list_batch_jobs(
    db_path: DbPathDep,
    status: str | None = Query(None),
    platform: str | None = Query(None),
    format: str | None = Query(None, alias="format"),
    limit: int = Query(50, ge=1, le=200),
) -> list[BatchSummary]:
    platform_filter = None
    if platform and platform.strip().lower() not in {"", "tutti", "all"}:
        try:
            platform_filter = Platform(platform.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    format_filter = None
    if format and format.strip().lower() not in {"", "tutti", "all"}:
        try:
            format_filter = MediaFormat(format.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    status_filter = None
    if status and status.strip().lower() not in {"", "tutti", "all"}:
        status_filter = status.strip().lower()
    rows = list_batches_filtered(
        db_path,
        status=status_filter,
        platform=platform_filter,
        media_format=format_filter,
        limit=limit,
    )
    return [BatchSummary(**r) for r in rows]


@router.get("/active", response_model=BatchSummary | None)
def active_batch(db_path: DbPathDep) -> BatchSummary | None:
    row = get_active_running_batch(db_path)
    if row is None:
        return None
    return BatchSummary(**row)


@router.post("/ai", response_model=StartAiBatchResponse)
def start_ai_batch(
    req: StartAiBatchRequest,
    settings: SettingsDep,
) -> StartAiBatchResponse:
    if req.clear_thumb_cache:
        clear_drive_thumb_cache(settings)
    try:
        platform = Platform(req.platform.strip().lower())
        media_format = MediaFormat(req.media_format.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    assets = [a.model_dump() for a in req.assets]
    try:
        batch_id = start_selected_ai_batch(
            settings,
            category=req.category.strip(),
            platform=platform,
            media_format=media_format,
            assets=assets,
            marketing_objectives=req.marketing_objectives,
            channels=req.channels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if settings.batch_auto_process:
        max_items = min(len(assets), int(settings.batch_auto_process_max_items))
        process_batch_queue(settings, max_items=max_items)

    return StartAiBatchResponse(batch_id=batch_id)


@router.get("/{batch_id}", response_model=BatchDetailResponse)
def batch_detail(batch_id: int, db_path: DbPathDep) -> BatchDetailResponse:
    data = get_batch_detail(db_path, batch_id=batch_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Batch #{batch_id} non trovato")
    return BatchDetailResponse(**data)


@router.post("/{batch_id}/stop", response_model=BatchStopResponse)
def batch_stop(
    batch_id: int,
    req: BatchStopRequest,
    db_path: DbPathDep,
) -> BatchStopResponse:
    ok = stop_batch(db_path, batch_id=batch_id, reason=req.reason)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"Batch #{batch_id} non trovato o non in stato running",
        )
    return BatchStopResponse(batch_id=batch_id, stop_requested=True)


async def _batch_event_stream(db_path, batch_id: int) -> AsyncIterator[dict]:
    last_signature: str | None = None
    while True:
        data = get_batch_detail(db_path, batch_id=batch_id)
        if data is None:
            yield {"event": "error", "data": json.dumps({"detail": "Batch non trovato"})}
            break
        signature = (
            f"{data['batch']['updated_at']}:"
            f"{data['batch']['status']}:"
            f"{data['batch']['done_count']}"
        )
        if signature != last_signature:
            yield {"event": "batch", "data": json.dumps(data)}
            last_signature = signature
        status = str(data["batch"]["status"]).lower()
        if status != "running":
            break
        await asyncio.sleep(2)


@router.get("/{batch_id}/events")
async def batch_events(batch_id: int, db_path: DbPathDep) -> EventSourceResponse:
    return EventSourceResponse(_batch_event_stream(db_path, batch_id))
