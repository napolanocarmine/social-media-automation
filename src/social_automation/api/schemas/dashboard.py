from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "social-media-automation-api"
    db_ok: bool | None = None
    db_backend: str | None = None


class DashboardStatsResponse(BaseModel):
    processed_visual: int = Field(ge=0)
    pending_approval: int = Field(ge=0)
    ready_to_plan: int = Field(ge=0)
    due_dispatch: int = Field(ge=0)
    running_batches: int = Field(ge=0)


class SuggestedNextStepResponse(BaseModel):
    page: str
