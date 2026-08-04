from __future__ import annotations

from pydantic import BaseModel, Field


class UploadDimensionValidation(BaseModel):
    valid: bool
    width: int
    height: int
    expected_width: int
    expected_height: int
    expected_label: str


class UploadValidateResponse(BaseModel):
    filename: str
    dimensions: UploadDimensionValidation


class UploadItemResult(BaseModel):
    image_id: int | None = None
    name: str
    processed_file: str | None = None
    dimensions: UploadDimensionValidation | None = None
    error: str | None = None


class UploadBatchResponse(BaseModel):
    run_ai_retouch: bool
    batch_id: int | None = None
    image_ids: list[int] = Field(default_factory=list)
    items: list[UploadItemResult] = Field(default_factory=list)
    redirect: str
