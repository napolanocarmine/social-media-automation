from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Platform(StrEnum):
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


class MediaFormat(StrEnum):
    """Formato del contenuto pubblicato (post nel feed vs storia 9:16)."""

    POST = "post"
    STORY = "story"


def infer_media_format_from_render_path(path: str | Path) -> MediaFormat:
    """Story se path in ``processed/stories/``, ``canva-rendered/stories/`` o suffisso ``*_story``."""
    p = str(path).replace("\\", "/").lower()
    if "/stories/" in p or "/processed/stories/" in p:
        return MediaFormat.STORY
    if "_story." in p or p.endswith("_story.jpg") or p.endswith("_story.jpeg") or p.endswith("_story.png"):
        return MediaFormat.STORY
    return MediaFormat.POST


class PipelineStep(StrEnum):
    SELECT_CATEGORY = "select_category"
    SELECT_ASSET = "select_asset"
    CANVA_RENDER = "canva_render"
    VALIDATE_IMAGE = "validate_image"
    META_PUBLISH = "meta_publish"
    SCHEDULE = "schedule"
    DONE = "done"


@dataclass
class DriveAsset:
    file_id: str
    name: str
    mime_type: str
    category: str | None = None
    path_segments: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    success: bool
    reason: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    """Esito pubblicazione su Meta (o errore)."""

    ok: bool
    platform: Platform
    rendered_path: Path | None = None
    validation: ValidationResult | None = None
    external_id: str | None = None
    detail: str | None = None


@dataclass
class ScheduleSlot:
    platforms: list[Platform]
    weekday: str  # lowercase english: monday, tuesday, ...
    time_hhmm: str  # "12:30"
    category: str | None = None  # categoria business opzionale (es. food, beer)


@dataclass
class EditorialSchedule:
    timezone: str
    slots: list[ScheduleSlot]
