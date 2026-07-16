"""Contesto parametrizzato per prompt Story AI (/produce, /copy)."""

from __future__ import annotations

from social_automation.brand.loader import StoryAgentConfig
from social_automation.models import MediaFormat, Platform

MARKETING_OBJECTIVES: tuple[str, ...] = (
    "Aumentare prenotazioni",
    "Engagement",
    "Community",
    "Notorietà",
)

DEFAULT_MARKETING_OBJECTIVE = "Engagement"


def normalize_marketing_objective(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in MARKETING_OBJECTIVES:
        return raw
    return DEFAULT_MARKETING_OBJECTIVE


def normalize_marketing_objectives(
    values: list[str] | None = None,
    *,
    legacy_single: str | None = None,
) -> list[str]:
    """Lista obiettivi validi; almeno un valore (default Engagement)."""
    out: list[str] = []
    for raw in values or []:
        val = (raw or "").strip()
        if val in MARKETING_OBJECTIVES and val not in out:
            out.append(val)
    if not out and legacy_single:
        single = normalize_marketing_objective(legacy_single)
        if single not in out:
            out.append(single)
    return out or [DEFAULT_MARKETING_OBJECTIVE]


def format_marketing_objectives_for_prompt(objectives: list[str]) -> str:
    if len(objectives) == 1:
        return objectives[0]
    return " · ".join(objectives)


def normalize_channels(
    channels: list[Platform] | list[str] | None,
    *,
    fallback_platform: Platform | None = None,
) -> list[Platform]:
    if not channels:
        if fallback_platform is not None:
            return [fallback_platform]
        return [Platform.INSTAGRAM, Platform.FACEBOOK]
    out: list[Platform] = []
    for ch in channels:
        if isinstance(ch, Platform):
            out.append(ch)
        else:
            val = str(ch).strip().lower()
            if val in {Platform.INSTAGRAM.value, Platform.FACEBOOK.value}:
                out.append(Platform(val))
    if not out and fallback_platform is not None:
        return [fallback_platform]
    return out or [Platform.INSTAGRAM, Platform.FACEBOOK]


def channels_label(channels: list[Platform]) -> str:
    labels: list[str] = []
    if Platform.INSTAGRAM in channels:
        labels.append("Instagram")
    if Platform.FACEBOOK in channels:
        labels.append("Facebook")
    return " + ".join(labels) if labels else "Instagram + Facebook"


def image_format_label(*, platform: Platform, media_format: MediaFormat) -> str:
    if media_format == MediaFormat.STORY:
        return "Story 1080x1920"
    if platform == Platform.FACEBOOK:
        return "Facebook Post 1200x900"
    return "Instagram Post 1080x1350"


def image_edit_format_label(*, platform: Platform, media_format: MediaFormat) -> str:
    """Etichetta formato nel prompt editing (allineata al Custom GPT)."""
    if media_format == MediaFormat.STORY:
        return "Story 9:16 (1080x1920)"
    if platform == Platform.FACEBOOK:
        return "Facebook Post (1200x900)"
    return "Instagram Feed 4:5 (1080x1350)"


def copy_format_label(media_format: MediaFormat) -> str:
    return "Story" if media_format == MediaFormat.STORY else "Post"


def _render_template(template: str, **kwargs: str) -> str:
    if not template.strip():
        return ""
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", value)
    return out.strip()


def build_produce_user_prompt(
    cfg: StoryAgentConfig,
    *,
    marketing_objective: str,
    channels: list[Platform],
    platform: Platform,
    media_format: MediaFormat,
    business_category: str | None = None,
    content_pillar: str = "",
    review_notes: str = "",
    suggested_crop: str = "",
    include_extras: bool = True,
) -> str:
    """Prompt /produce per Visual Producer (image edit AI)."""
    body = _render_template(
        cfg.produce_prompt,
        objective=marketing_objective,
        channels=channels_label(channels),
        format=image_format_label(platform=platform, media_format=media_format),
    )
    if not include_extras:
        return body
    extras: list[str] = []
    if business_category:
        extras.append(f"Categoria: {business_category}")
    if content_pillar:
        extras.append(f"Content pillar: {content_pillar}")
    if suggested_crop:
        extras.append(f"Crop suggerito dalla review: {suggested_crop}")
    if review_notes:
        extras.append(f"Note review visiva: {review_notes}")
    if extras:
        body = f"{body}\n\n" + "\n".join(extras)
    return body


def build_copy_user_prompt(
    cfg: StoryAgentConfig,
    *,
    marketing_objective: str,
    channels: list[Platform],
    media_format: MediaFormat,
    business_category: str | None = None,
    content_pillar: str = "",
) -> str:
    """Prompt /copy per caption pack."""
    body = _render_template(
        cfg.copy_prompt,
        objective=marketing_objective,
        channels=channels_label(channels),
        format=copy_format_label(media_format),
    )
    extras: list[str] = []
    if business_category:
        extras.append(f"Categoria: {business_category}")
    if content_pillar:
        extras.append(f"Content pillar: {content_pillar}")
    if extras:
        body = f"{body}\n\n" + "\n".join(extras)
    return body
