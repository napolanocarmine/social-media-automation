"""Schemi API automazione."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PrepareWeekRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    dry_run: bool = True
    try_render: bool = True


class PrepareWeekResponse(BaseModel):
    message: str
    dry_run: bool
    schedule_path: str
    planned: int = 0
    processed: int = 0
    rendered: int = 0
    skipped_occupied: int = 0
    skipped_quality: int = 0
    skipped_borderline: int = 0
    skipped_no_asset: int = 0
    auto_approved: int = 0
    vision_evaluated: int = 0
    errors: list[str] = Field(default_factory=list)
    assignments: list[dict] = Field(default_factory=list)
