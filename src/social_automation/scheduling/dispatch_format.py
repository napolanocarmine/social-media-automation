"""Risoluzione post vs story per dispatch e calendario."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from social_automation.models import MediaFormat, infer_media_format_from_render_path


def media_format_from_planning_detail(detail: str | None) -> MediaFormat | None:
    """Legge ``media_format`` da ``planning_events.detail`` (JSON)."""
    raw = (detail or "").strip()
    if not raw.startswith("{") or not raw.endswith("}"):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    fmt = str(payload.get("media_format") or "").strip().lower()
    if fmt == MediaFormat.STORY.value:
        return MediaFormat.STORY
    if fmt == MediaFormat.POST.value:
        return MediaFormat.POST
    return None


def resolve_dispatch_media_format(
    row: dict[str, Any],
    *,
    image_path: str | Path | None = None,
    force_story: bool = False,
) -> MediaFormat:
    """
    Ordine di priorità:
    1. ``force_story`` (regole story)
    2. ``media_format`` in ``planning_events.detail`` (scelta utente in Pianifica)
    3. ``metadata.media_format`` (ultimo processamento)
    4. flag render solo-story (story sì, post no)
    5. euristica sul path file (legacy / Blob)
    """
    if force_story:
        return MediaFormat.STORY

    from_detail = media_format_from_planning_detail(str(row.get("detail") or ""))
    if from_detail is not None:
        return from_detail

    meta_fmt = str(row.get("metadata_media_format") or "").strip().lower()
    if meta_fmt == MediaFormat.STORY.value:
        return MediaFormat.STORY
    if meta_fmt == MediaFormat.POST.value:
        return MediaFormat.POST

    render_ig = int(row.get("render_ig") or 0) == 1
    render_fb = int(row.get("render_fb") or 0) == 1
    render_ig_story = int(row.get("render_ig_story") or 0) == 1
    render_fb_story = int(row.get("render_fb_story") or 0) == 1
    has_story_render = render_ig_story or render_fb_story
    has_post_render = render_ig or render_fb
    if has_story_render and not has_post_render:
        return MediaFormat.STORY

    path_raw = str(image_path if image_path is not None else row.get("image_path") or "")
    return infer_media_format_from_render_path(path_raw)
