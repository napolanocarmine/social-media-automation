"""Costruzione caption da copy pack Story AI."""

from __future__ import annotations

from typing import Any

from social_automation.models import MediaFormat, Platform


def _hashtags_line(tags: Any) -> str:
    if not tags:
        return ""
    if isinstance(tags, str):
        return tags.strip()
    parts = [str(t).strip() for t in tags if str(t).strip()]
    return " ".join(parts)


def caption_for_platform(
    copy_data: dict[str, Any] | None,
    *,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
) -> str:
    """Testo pubblicazione da ``copy_json`` (caption + hashtag)."""
    if not copy_data:
        return ""
    if media_format == MediaFormat.STORY:
        base = str(copy_data.get("story_text") or "").strip()
    elif platform == Platform.FACEBOOK:
        base = str(copy_data.get("facebook_caption") or "").strip()
    else:
        base = str(copy_data.get("instagram_caption") or "").strip()
    tags = _hashtags_line(copy_data.get("hashtags"))
    if base and tags:
        if tags.startswith("#"):
            return f"{base}\n\n{tags}"
        return f"{base}\n\n{tags}"
    return base or tags


def copy_approved(copy_data: dict[str, Any] | None) -> bool:
    if not copy_data:
        return False
    fr = copy_data.get("final_review")
    if isinstance(fr, dict):
        return str(fr.get("status", "")).upper() == "APPROVED"
    return False


def planning_detail_with_caption(caption: str) -> str:
    import json

    cap = (caption or "").strip()
    if not cap:
        return ""
    return json.dumps({"caption": cap}, ensure_ascii=False)


def caption_from_planning_detail(detail: str | None) -> str:
    """Estrae caption testuale da ``detail`` (JSON o testo legacy)."""
    import json

    raw = (detail or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return str(payload.get("caption", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw
