from __future__ import annotations

from fastapi import APIRouter

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.dashboard import (
    DashboardStatsResponse,
    SuggestedNextStepResponse,
)
from social_automation.services.dashboard import get_workflow_stats, suggest_next_page

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
def dashboard_stats(settings: SettingsDep, db_path: DbPathDep) -> DashboardStatsResponse:
    stats = get_workflow_stats(db_path, settings)
    return DashboardStatsResponse(**stats)


@router.get("/suggested-next-step", response_model=SuggestedNextStepResponse)
def suggested_next_step(
    settings: SettingsDep,
    db_path: DbPathDep,
) -> SuggestedNextStepResponse:
    stats = get_workflow_stats(db_path, settings)
    return SuggestedNextStepResponse(page=suggest_next_page(stats))
