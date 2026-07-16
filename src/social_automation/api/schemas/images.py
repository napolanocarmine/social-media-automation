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


class ApprovalResponse(BaseModel):
    id: int
    approval_status: str
