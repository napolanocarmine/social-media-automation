"""Resolver template Canva da config YAML."""

from __future__ import annotations

from social_automation.models import MediaFormat

_STORY_KEY = "story"


def _normalize_format(media_format: MediaFormat | str | None) -> str:
    if media_format is None:
        return MediaFormat.POST.value
    if isinstance(media_format, MediaFormat):
        return media_format.value
    return str(media_format).strip().lower() or MediaFormat.POST.value


def resolve_template_id(
    config: dict,
    *,
    platform: str,
    category: str | None = None,
    media_format: MediaFormat | str | None = MediaFormat.POST,
) -> str | None:
    """Risolve il template Canva dato platform/category e formato (post|story).

    - Per ``post``: usa la chiave specifica della piattaforma (instagram/facebook).
    - Per ``story``: usa la chiave condivisa ``story`` (IG e FB usano lo stesso
      template verticale 9:16).
    """
    fmt = _normalize_format(media_format)
    if fmt == MediaFormat.STORY.value:
        platform_key = _STORY_KEY
    else:
        platform_key = platform.strip().lower()
    category_key = (category or "").strip().lower()

    overrides = config.get("category_template_overrides", {}) or {}
    if category_key:
        category_map = overrides.get(category_key, {}) or {}
        from_override = str(category_map.get(platform_key, "")).strip()
        if from_override:
            return from_override

    templates = config.get("templates", {}) or {}
    platform_map = templates.get(platform_key, {}) or {}
    default_template = str(platform_map.get("default_template_id", "")).strip()
    return default_template or None
