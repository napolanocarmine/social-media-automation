"""Router pianificazione."""

from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, HTTPException

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.plans import (
    CreatePlanRequest,
    PlanActionResponse,
    ReschedulePlanRequest,
    SuggestSlotRequest,
    SuggestSlotResponse,
)
from social_automation.models import MediaFormat, Platform
from social_automation.services.planning import (
    cancel_plan,
    reschedule_plan,
    save_plan,
    suggest_editorial_slot,
)

router = APIRouter(prefix="/plans", tags=["plans"])


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Data non valida: {value}") from e


def _parse_time(value: str) -> time:
    raw = value.strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=422, detail=f"Ora non valida: {value}")
    try:
        return time(int(parts[0]), int(parts[1]))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Ora non valida: {value}") from e


@router.post("/suggest-slot", response_model=SuggestSlotResponse | None)
def suggest_slot(
    body: SuggestSlotRequest,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> SuggestSlotResponse | None:
    try:
        platform = Platform(body.platform.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        result = suggest_editorial_slot(db_path, platform=platform, settings=settings)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if result is None:
        return None
    return SuggestSlotResponse(**result)


@router.post("", response_model=PlanActionResponse)
def create_plan(
    body: CreatePlanRequest,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> PlanActionResponse:
    try:
        platform = Platform(body.platform.strip().lower())
        media_format = MediaFormat(body.media_format.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    plan_date = _parse_date(body.scheduled_date) if body.scheduled_date else None
    plan_time = _parse_time(body.scheduled_time) if body.scheduled_time else None
    story_mode = None
    story_weekday = None
    story_time = None
    story_tz = None
    if body.story_schedule is not None:
        story_mode = body.story_schedule.mode
        story_weekday = body.story_schedule.weekday
        story_time = body.story_schedule.time_local
        story_tz = body.story_schedule.timezone

    try:
        result = save_plan(
            db_path,
            image_id=body.image_id,
            platform=platform,
            media_format=media_format,
            plan_date=plan_date,
            plan_time=plan_time,
            caption=body.caption,
            story_schedule_mode=story_mode,
            story_weekday=story_weekday,
            story_time_local=story_time,
            story_timezone=story_tz,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return PlanActionResponse(
        message=result["message"],
        event_id=result.get("event_id"),
        image_id=int(result["image_id"]),
        platform=str(result["platform"]),
        scheduled_for=result.get("scheduled_for"),
    )


@router.patch("/{image_id}/{platform}", response_model=PlanActionResponse)
def reschedule(
    image_id: int,
    platform: str,
    body: ReschedulePlanRequest,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> PlanActionResponse:
    try:
        plat = Platform(platform.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        result = reschedule_plan(
            db_path,
            image_id=image_id,
            platform=plat,
            plan_date=_parse_date(body.scheduled_date),
            plan_time=_parse_time(body.scheduled_time),
            caption=body.caption,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return PlanActionResponse(
        message=result["message"],
        event_id=int(result["event_id"]),
        image_id=int(result["image_id"]),
        platform=str(result["platform"]),
        scheduled_for=result.get("scheduled_for"),
    )


@router.delete("/{image_id}/{platform}", response_model=PlanActionResponse)
def cancel(
    image_id: int,
    platform: str,
    db_path: DbPathDep,
    settings: SettingsDep,
) -> PlanActionResponse:
    try:
        plat = Platform(platform.strip().lower())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        result = cancel_plan(
            db_path,
            image_id=image_id,
            platform=plat,
            settings=settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return PlanActionResponse(
        message=result["message"],
        image_id=int(result["image_id"]),
        platform=str(result["platform"]),
    )
