"""Router automazione."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from social_automation.api.deps import SettingsDep
from social_automation.api.schemas.automation import PrepareWeekRequest, PrepareWeekResponse
from social_automation.services.automation import run_prepare_week

router = APIRouter(prefix="/automation", tags=["automation"])


@router.post("/prepare-week", response_model=PrepareWeekResponse)
def prepare_week_endpoint(
    body: PrepareWeekRequest,
    settings: SettingsDep,
) -> PrepareWeekResponse:
    try:
        data = run_prepare_week(
            days=body.days,
            dry_run=body.dry_run,
            try_render=body.try_render,
            settings=settings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PrepareWeekResponse(**data)
