"""Router calendario."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.plans import CalendarEventOut, CalendarResponse
from social_automation.models import Platform
from social_automation.services.calendar import list_active_plans, list_calendar

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("", response_model=CalendarResponse)
def get_calendar(
    db_path: DbPathDep,
    settings: SettingsDep,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    platform: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(500, ge=1, le=1000),
) -> CalendarResponse:
    platform_filter = None
    if platform and platform.strip().lower() not in {"", "tutti", "all"}:
        try:
            platform_filter = Platform(platform.strip().lower())
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    category_filter = None
    if category and category.strip().lower() not in {"", "tutte", "all"}:
        category_filter = category.strip().lower()

    data = list_calendar(
        db_path,
        year=year,
        month=month,
        platform=platform_filter,
        business_category=category_filter,
        limit=limit,
        settings=settings,
    )
    by_day = {str(k): [CalendarEventOut(**ev) for ev in v] for k, v in data["by_day"].items()}
    return CalendarResponse(
        year=data["year"],
        month=data["month"],
        total=data["total"],
        items=[CalendarEventOut(**ev) for ev in data["items"]],
        by_day=by_day,
    )


@router.get("/events", response_model=list[CalendarEventOut])
def list_events(
    db_path: DbPathDep,
    settings: SettingsDep,
    all_active: bool = Query(False),
    year: int | None = Query(None),
    month: int | None = Query(None),
    platform: str | None = Query(None),
) -> list[CalendarEventOut]:
    platform_filter = None
    if platform and platform.strip().lower() not in {"", "tutti", "all"}:
        try:
            platform_filter = Platform(platform.strip().lower())
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        items = list_active_plans(
            db_path,
            platform=platform_filter,
            all_active=all_active,
            year=year,
            month=month,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [CalendarEventOut(**ev) for ev in items]
