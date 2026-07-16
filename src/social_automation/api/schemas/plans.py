"""Schemi API pianificazione e calendario."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuggestSlotRequest(BaseModel):
    platform: str = Field(..., description="instagram | facebook")


class SuggestSlotResponse(BaseModel):
    platform: str
    scheduled_for: str
    scheduled_date: str
    scheduled_time: str
    weekday: str
    weekday_label: str
    time_hhmm: str
    timezone: str


class GenerateCopyRequest(BaseModel):
    platform: str = "instagram"
    media_format: str = "post"
    marketing_objectives: list[str] = Field(default_factory=list)
    marketing_objective: str | None = None
    channels: list[str] | None = None


class StoryScheduleWeekly(BaseModel):
    mode: str = "weekly"
    weekday: int = Field(0, ge=0, le=6)
    time_local: str = "10:00"
    timezone: str | None = None


class CreatePlanRequest(BaseModel):
    image_id: int
    platform: str
    media_format: str = "post"
    scheduled_date: str | None = None
    scheduled_time: str | None = None
    caption: str | None = None
    story_schedule: StoryScheduleWeekly | None = None


class ReschedulePlanRequest(BaseModel):
    scheduled_date: str
    scheduled_time: str
    caption: str | None = None


class PlanActionResponse(BaseModel):
    message: str
    event_id: int | None = None
    image_id: int
    platform: str
    scheduled_for: str | None = None


class CalendarEventOut(BaseModel):
    id: int
    image_id: int
    image_name: str
    platform: str
    event_type: str
    scheduled_for: str
    time_label: str
    day: int | None = None
    external_id: str | None = None
    detail: str | None = None
    caption: str | None = None
    media_format: str
    media: dict[str, str | None]


class CalendarResponse(BaseModel):
    year: int
    month: int
    total: int
    items: list[CalendarEventOut]
    by_day: dict[str, list[CalendarEventOut]]
