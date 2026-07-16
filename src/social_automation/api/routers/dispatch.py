"""Router dispatch."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.dispatch import (
    DispatchRunRequest,
    DispatchRunResponse,
    DueEventsResponse,
)
from social_automation.models import Platform
from social_automation.services.dispatch import list_due, preview_dispatch, run_dispatch

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


def _platform_filter(value: str | None) -> Platform | None:
    if not value or value.strip().lower() in {"", "tutti", "all"}:
        return None
    try:
        return Platform(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/due", response_model=DueEventsResponse)
def due_events(
    db_path: DbPathDep,
    settings: SettingsDep,
    platform: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> DueEventsResponse:
    data = list_due(
        db_path,
        platform=_platform_filter(platform),
        limit=limit,
        settings=settings,
    )
    return DueEventsResponse(**data)


@router.post("/dry-run", response_model=DispatchRunResponse)
def dispatch_dry_run(
    body: DispatchRunRequest,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> DispatchRunResponse:
    data = preview_dispatch(
        db_path,
        platform=_platform_filter(body.platform),
        limit=body.limit,
        settings=settings,
    )
    return DispatchRunResponse(**data)


@router.post("/run", response_model=DispatchRunResponse)
def dispatch_run(
    body: DispatchRunRequest,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> DispatchRunResponse:
    try:
        data = run_dispatch(
            db_path,
            platform=_platform_filter(body.platform),
            limit=body.limit,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DispatchRunResponse(**data)
