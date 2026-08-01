from __future__ import annotations

from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual.category_skills import format_category_skill_for_image_edit
from social_automation.visual.edit_plan import build_image_edit_plan_user_prompt
from social_automation.visual.prompts import build_image_edit_user_prompt, image_edit_api_preamble


def test_social_appetizing_uses_social_preamble() -> None:
    s = Settings(visual_social_appetizing=True)
    text = image_edit_api_preamble(s)
    assert "appetizing" in text.lower()
    assert "crave-worthy" in text.lower()


def test_social_appetizing_loads_social_template() -> None:
    s = Settings(visual_social_appetizing=True)
    prompt = build_image_edit_user_prompt(
        review={},
        business_category="food",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        content_pillar="food",
        settings=s,
    )
    assert "SOCIAL APPETIZING" in prompt or "appetit" in prompt.lower()
    assert "recupero ombre" in prompt.lower() or "lift shadows" in prompt.lower()


def test_edit_plan_social_mode_higher_tone_defaults() -> None:
    text = build_image_edit_plan_user_prompt(
        business_category="food",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        content_pillar="food",
        social_appetizing=True,
    )
    assert "SOCIAL APPETIZING" in text
    assert '"exposure": 0.12' in text
    assert '"saturation": 0.04' in text


def test_category_skill_social_food_suffix() -> None:
    text = format_category_skill_for_image_edit("food", social_appetizing=True)
    assert "Social appetizing" in text
    assert "crave-worthy" in text
