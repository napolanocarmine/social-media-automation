"""Visual review e decision engine (Story AI V2)."""

from __future__ import annotations

from pathlib import Path

from social_automation.brand.loader import pillar_for_category
from social_automation.brand.openai_json import api_configured, chat_vision_json
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual.models import VisualDecision, VisualReview
from social_automation.visual.prompts import (
    build_visual_review_system_message,
    build_visual_review_user_prompt,
)


def run_visual_review(
    image_path: Path,
    *,
    settings: Settings,
    business_category: str | None = None,
    platform: Platform = Platform.INSTAGRAM,
    media_format: MediaFormat = MediaFormat.POST,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> VisualReview:
    """Analisi visiva: score, needs_editing, formato suggerito."""
    if not api_configured(api_key=settings.vision_api_key, model=settings.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Visual Review")
    pillar = pillar_for_category(business_category)
    user = build_visual_review_user_prompt(
        business_category=business_category,
        platform=platform,
        media_format=media_format,
        content_pillar=pillar,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
    data = chat_vision_json(
        image_path=image_path,
        system_message=build_visual_review_system_message(settings),
        user_prompt=user,
        api_key=settings.vision_api_key,
        model=settings.vision_model,
        api_base_url=settings.vision_api_base_url,
        max_tokens=600,
        settings=settings,
    )
    return VisualReview.from_dict(data)


def decision_engine(review: VisualReview, *, settings: Settings) -> VisualDecision:
    """
    Regole roadmap V2:
    - score >= soglia (default 8): usa originale
    - score < soglia: editing AI
    - score < soglia manual (default 5): flag review manuale
    """
    use_original = review.score >= float(settings.visual_review_score_use_original)
    needs_manual = review.score < float(settings.visual_review_score_manual)
    needs_ai = not use_original and review.needs_editing

    if use_original:
        status = "manual_review" if needs_manual else "original"
    elif needs_ai:
        status = "ai_editing"
    else:
        status = "manual_review"

    return VisualDecision(
        use_original=use_original,
        needs_ai_editing=needs_ai,
        needs_manual_review=needs_manual,
        visual_status=status,
    )
