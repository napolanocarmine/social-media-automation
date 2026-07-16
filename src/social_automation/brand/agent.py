"""Story AI Assistant: ritocco (JSON) e copy pack."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from social_automation.brand.loader import (
    StoryAgentConfig,
    build_system_message,
    load_story_agent_config,
    pillar_for_category,
)
from social_automation.brand.openai_json import api_configured, chat_vision_json
from social_automation.brand.prompt_context import (
    build_copy_user_prompt,
    channels_label,
    format_marketing_objectives_for_prompt,
    image_format_label,
    normalize_channels,
    normalize_marketing_objectives,
)
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings


def _platform_format_hint(platform: Platform, media_format: MediaFormat) -> str:
    if media_format == MediaFormat.STORY:
        return "instagram_story"
    if platform == Platform.FACEBOOK:
        return "facebook_post"
    return "instagram_post"


def _objective_label(
    *,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
) -> str:
    return format_marketing_objectives_for_prompt(
        normalize_marketing_objectives(
            marketing_objectives,
            legacy_single=marketing_objective,
        )
    )


def run_retouch_analysis(
    image_path: Path,
    *,
    settings: Settings,
    business_category: str | None = None,
    platform: Platform = Platform.INSTAGRAM,
    media_format: MediaFormat = MediaFormat.POST,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    agent_cfg: StoryAgentConfig | None = None,
) -> dict[str, Any]:
    """PROMPT 1: analisi visiva + parametri ritocco leggeri."""
    if not api_configured(api_key=settings.vision_api_key, model=settings.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Story AI")
    cfg = agent_cfg or load_story_agent_config()
    system = build_system_message(cfg)
    pillar = pillar_for_category(business_category)
    fmt = _platform_format_hint(platform, media_format)
    ch = normalize_channels(channels, fallback_platform=platform)
    objective = _objective_label(
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
    )
    user = (
        f"{cfg.retouch_prompt}\n\n"
        f"OBIETTIVO: {objective}\n"
        f"CANALI: {channels_label(ch)}\n"
        f"FORMATO: {image_format_label(platform=platform, media_format=media_format)}\n"
        f"Categoria business: {business_category or 'non specificata'}\n"
        f"Content pillar: {pillar}\n"
        f"Formato destinazione prioritario: {fmt}\n"
        "La foto è senza overlay: solo fotografia."
    )
    return chat_vision_json(
        image_path=image_path,
        system_message=system,
        user_prompt=user,
        api_key=settings.vision_api_key,
        model=settings.vision_model,
        api_base_url=settings.vision_api_base_url,
        max_tokens=800,
        settings=settings,
    )


def generate_copy_pack(
    image_path: Path,
    *,
    settings: Settings,
    business_category: str | None = None,
    platform: Platform = Platform.INSTAGRAM,
    media_format: MediaFormat = MediaFormat.POST,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    agent_cfg: StoryAgentConfig | None = None,
) -> dict[str, Any]:
    """PROMPT 2: caption IG/FB, story, CTA, hashtag."""
    if not api_configured(api_key=settings.vision_api_key, model=settings.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Story AI")
    cfg = agent_cfg or load_story_agent_config()
    system = build_system_message(cfg)
    pillar = pillar_for_category(business_category)
    user = build_copy_user_prompt(
        cfg,
        marketing_objective=_objective_label(
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
        ),
        channels=normalize_channels(channels, fallback_platform=platform),
        media_format=media_format,
        business_category=business_category,
        content_pillar=pillar,
    )
    return chat_vision_json(
        image_path=image_path,
        system_message=system,
        user_prompt=user,
        api_key=settings.vision_api_key,
        model=settings.vision_model,
        api_base_url=settings.vision_api_base_url,
        max_tokens=1000,
        settings=settings,
    )


def run_auto_pack(
    image_path: Path,
    *,
    settings: Settings,
    business_category: str | None = None,
    platform: Platform = Platform.INSTAGRAM,
    media_format: MediaFormat = MediaFormat.POST,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    agent_cfg: StoryAgentConfig | None = None,
) -> dict[str, Any]:
    """Modalità /auto: ritocco + copy in una chiamata."""
    if not api_configured(api_key=settings.vision_api_key, model=settings.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Story AI")
    cfg = agent_cfg or load_story_agent_config()
    system = build_system_message(cfg)
    pillar = pillar_for_category(business_category)
    fmt = _platform_format_hint(platform, media_format)
    ch = normalize_channels(channels, fallback_platform=platform)
    objective = _objective_label(
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
    )
    user = (
        f"{cfg.auto_prompt}\n\n"
        f"OBIETTIVO: {objective}\n"
        f"CANALI: {channels_label(ch)}\n"
        f"Categoria: {business_category or 'non specificata'}\n"
        f"Content pillar: {pillar}\n"
        f"Formato prioritario: {fmt}\n"
    )
    return chat_vision_json(
        image_path=image_path,
        system_message=system,
        user_prompt=user,
        api_key=settings.vision_api_key,
        model=settings.vision_model,
        api_base_url=settings.vision_api_base_url,
        max_tokens=1500,
        settings=settings,
    )
