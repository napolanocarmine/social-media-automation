"""Facade edit immagine: Responses API (default) o Images API legacy."""

from __future__ import annotations

from pathlib import Path

from social_automation.settings import Settings
from social_automation.visual.image_generation import (
    edit_image_with_prompt,
)
from social_automation.visual.image_generation import (
    image_edit_configured as images_api_configured,
)
from social_automation.visual.models import ImageEditApiResult
from social_automation.visual.responses_image import (
    edit_image_via_responses,
    responses_image_configured,
)


def image_edit_configured(settings: Settings) -> bool:
    backend = (settings.visual_image_backend or "responses").strip().lower()
    if backend == "images_edits":
        return images_api_configured(settings)
    return responses_image_configured(settings)


def run_image_edit(
    source_path: Path,
    *,
    instructions: str,
    user_prompt: str,
    legacy_prompt: str,
    dest_path: Path,
    settings: Settings,
    crop_mode: str = "instagram_4_5",
    jpeg_quality: int | None = None,
) -> ImageEditApiResult:
    """Esegue edit con il backend configurato."""
    quality = jpeg_quality if jpeg_quality is not None else int(settings.visual_jpeg_export_quality)
    backend = (settings.visual_image_backend or "responses").strip().lower()
    if backend == "images_edits":
        path = edit_image_with_prompt(
            source_path,
            prompt=legacy_prompt,
            dest_path=dest_path,
            settings=settings,
            crop_mode=crop_mode,
            jpeg_quality=quality,
        )
        return ImageEditApiResult(path=path)
    return edit_image_via_responses(
        source_path,
        instructions=instructions,
        user_prompt=user_prompt,
        dest_path=dest_path,
        settings=settings,
        crop_mode=crop_mode,
        jpeg_quality=quality,
    )
