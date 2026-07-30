from __future__ import annotations

from social_automation.settings import Settings
from social_automation.visual.routing import should_run_edit_plan


def test_smart_routing_skips_edit_plan_for_food_batch() -> None:
    s = Settings(
        visual_edit_plan_enabled=True,
        visual_smart_routing=True,
        visual_review_enabled=False,
        visual_gpt_pure_mode=False,
    )
    assert should_run_edit_plan(s, business_category="food") is False


def test_edit_plan_runs_for_staff_category() -> None:
    s = Settings(
        visual_edit_plan_enabled=True,
        visual_smart_routing=True,
        visual_review_enabled=False,
    )
    assert should_run_edit_plan(s, business_category="peppe") is True


def test_edit_plan_disabled_by_flag() -> None:
    s = Settings(visual_edit_plan_enabled=False, visual_smart_routing=True)
    assert should_run_edit_plan(s, business_category="food") is False
