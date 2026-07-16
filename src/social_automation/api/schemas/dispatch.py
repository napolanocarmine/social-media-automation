"""Schemi API dispatch."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DuePlanningEvent(BaseModel):
    id: int
    image_id: int
    image_name: str
    platform: str
    event_type: str
    scheduled_for: str
    external_id: str | None = None
    detail: str | None = None
    dispatch_gate: str


class DueStoryRule(BaseModel):
    rule_id: int
    image_id: int
    platform: str
    schedule_mode: str
    occurrence_key: str
    slot_label: str
    scheduled_for: str
    image_path: str
    caption: str


class DueEventsResponse(BaseModel):
    planning_events: list[DuePlanningEvent]
    story_rules: list[DueStoryRule]
    planning_count: int
    story_count: int


class DispatchRunRequest(BaseModel):
    platform: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class DispatchRunResponse(BaseModel):
    dry_run: bool
    message: str
    planning_published: int = 0
    planning_failed: int = 0
    planning_skipped: int = 0
    story_published: int = 0
    story_failed: int = 0
    story_skipped_reserve: int = 0
    skip_reasons: list[str] = Field(default_factory=list)
    planning_events: list[DuePlanningEvent] | None = None
    story_rules: list[DueStoryRule] | None = None
    planning_count: int | None = None
    story_count: int | None = None
