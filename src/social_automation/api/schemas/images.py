from __future__ import annotations

from pydantic import BaseModel, Field


class ImageMediaUrls(BaseModel):
    processed: str
    original: str


class ImageSummary(BaseModel):
    id: int
    name: str
    path: str
    business_category: str | None = None
    approval_status: str
    visual_score: float | None = None
    visual_status: str | None = None
    editing_required: bool | None = None
    visual_method: str | None = None
    revised_prompt: str | None = None
    edit_plan_summary: str | None = None
    producer_notes: str | None = None
    has_processed_file: bool
    has_original_file: bool
    media: ImageMediaUrls
    created_at: str = ""
    updated_at: str = ""


class ImageListResponse(BaseModel):
    items: list[ImageSummary]
    total: int
    limit: int | None = None
    offset: int | None = None
    page: int | None = None
    page_size: int | None = None
    total_pages: int | None = None


class ApprovalRequest(BaseModel):
    action: str = Field(description="approve | reject | use_original")
    reason: str | None = Field(default=None, description="Motivo opzionale (reject / use_original)")
    tags: list[str] | None = Field(
        default=None,
        description="Tag feedback predefiniti (es. logo_altered, too_hdr)",
    )


class ApprovalFeedbackTagsResponse(BaseModel):
    tags: dict[str, str]


class ApprovalResponse(BaseModel):
    id: int
    approval_status: str
