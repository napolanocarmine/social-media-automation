from __future__ import annotations

from social_automation.brand.loader import load_story_agent_config
from social_automation.brand.prompt_context import build_copy_user_prompt
from social_automation.models import MediaFormat, Platform


def test_copy_prompt_is_grounded_on_product_and_image() -> None:
    cfg = load_story_agent_config()
    prompt = build_copy_user_prompt(
        cfg,
        marketing_objective="Engagement",
        channels=[Platform.INSTAGRAM, Platform.FACEBOOK],
        media_format=MediaFormat.POST,
        business_category="food",
        content_pillar="food",
    )
    assert "VISUAL GROUNDING" in prompt
    assert "PRODUCT GROUNDING" in prompt
    assert "il prodotto DEVE comparire nel copy" in prompt
    assert "NON inventare ingredienti" in prompt
    assert "Categoria: food" in prompt
    assert "Content pillar: food" in prompt


def test_business_rules_do_not_hide_product() -> None:
    cfg = load_story_agent_config()
    rules = cfg.business_rules_text
    assert "NON ignorarli quando sono protagonisti della foto" in rules
    assert "Mai trasformare un'ipotesi in un fatto" in rules
