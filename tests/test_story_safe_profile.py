from __future__ import annotations

from social_automation.settings import Settings
from social_automation.settings_profiles import apply_visual_pipeline_profile


def test_story_safe_profile_is_pixel_first() -> None:
    s = Settings(visual_pipeline_profile="story_safe")
    resolved = apply_visual_pipeline_profile(s)
    assert resolved.visual_produce_mode == "pixel"
    assert resolved.visual_use_ai_image_edit is False
    assert resolved.visual_review_enabled is True
    assert resolved.visual_parallel_copy is False
    assert resolved.visual_social_appetizing is False
    assert resolved.visual_smart_routing is True


def test_story_safe_is_default_profile() -> None:
    assert Settings().visual_pipeline_profile == "story_safe"
