from __future__ import annotations

from pydantic import BaseModel, Field


class DriveAssetSummary(BaseModel):
    file_id: str
    name: str
    mime_type: str
    category: str | None = None
    path_segments: list[str] = Field(default_factory=list)
    path_hint: str = ""


class DriveAssetListResponse(BaseModel):
    items: list[DriveAssetSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class CategoriesResponse(BaseModel):
    categories: list[str]


class DriveAssetInput(BaseModel):
    file_id: str
    name: str = ""
    mime_type: str = "image/jpeg"
    category: str | None = None
    path_segments: list[str] = Field(default_factory=list)


class StartAiBatchRequest(BaseModel):
    category: str
    platform: str
    media_format: str = "post"
    assets: list[DriveAssetInput]
    marketing_objectives: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    clear_thumb_cache: bool = False


class StartAiBatchResponse(BaseModel):
    batch_id: int


class BatchSummary(BaseModel):
    id: int
    status: str
    category: str | None = None
    platform: str | None = None
    media_format: str | None = None
    requested_count: int
    completed_count: int
    failed_count: int
    done_count: int
    progress_pct: int
    started_at: str = ""
    finished_at: str = ""
    runner_pid: int | None = None
    stop_requested_at: str | None = None
    stop_reason: str | None = None
    last_error: str | None = None
    note: str | None = None
    updated_at: str = ""


class BatchItemSummary(BaseModel):
    id: int
    batch_id: int
    item_index: int
    status: str
    source_asset_id: str | None = None
    source_asset_name: str | None = None
    business_category: str | None = None
    image_id: int | None = None
    rendered_file: str | None = None
    error_message: str | None = None
    media_format: str | None = None
    created_at: str = ""


class BatchDetailResponse(BaseModel):
    batch: BatchSummary
    items: list[BatchItemSummary]


class BatchStopRequest(BaseModel):
    reason: str | None = None


class BatchStopResponse(BaseModel):
    batch_id: int
    stop_requested: bool
