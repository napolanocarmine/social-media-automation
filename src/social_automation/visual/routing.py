"""Routing intelligente step pipeline visuale."""

from __future__ import annotations

from social_automation.settings import Settings
from social_automation.visual.models import VisualReview

_STATIC_FOOD_CATEGORIES = frozenset({"food", "birra", "beer"})


def should_run_edit_plan(
    settings: Settings,
    *,
    business_category: str | None,
    review: VisualReview | None = None,
) -> bool:
    """
    Decide se eseguire vision pre-edit (Image Edit Plan).

    Con ``visual_smart_routing`` attivo salta il piano per:
    - categorie food statiche (fast path batch)
    - foto già approvate dalla Visual Review (score alto, no editing)
    """
    if settings.visual_gpt_pure_mode:
        return False
    if not settings.visual_edit_plan_enabled:
        return False
    if review is not None:
        if review.score >= float(settings.visual_review_score_use_original):
            return False
        if not review.needs_editing:
            return False
    if settings.visual_smart_routing:
        cat = (business_category or "").strip().lower()
        if cat in _STATIC_FOOD_CATEGORIES and not settings.visual_review_enabled:
            return False
    return True


def should_run_visual_review(settings: Settings) -> bool:
    return bool(settings.visual_review_enabled)


def should_run_prompt_compiler(settings: Settings) -> bool:
    if settings.visual_gpt_pure_mode:
        return False
    return bool(settings.visual_edit_prompt_compiler)


def resolve_produce_mode(settings: Settings) -> str:
    return (settings.visual_produce_mode or "generative").strip().lower()
