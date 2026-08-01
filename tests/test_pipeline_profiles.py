from __future__ import annotations

import os

from social_automation.settings import Settings, load_settings
from social_automation.settings_profiles import apply_visual_pipeline_profile


def test_quality_profile_enables_gpt_parity_flags() -> None:
    s = Settings(visual_pipeline_profile="quality")
    out = apply_visual_pipeline_profile(s)
    assert out.visual_edit_prompt_compiler is True
    assert out.visual_smart_routing is False
    assert out.visual_precrop_before_api is False
    assert out.visual_skip_post_crop is True
    assert out.visual_image_input_fidelity == "high"
    assert out.visual_social_appetizing is True
    assert out.visual_disable_pillow_retouch is True
    assert out.visual_edit_plan_model == "gpt-4o"
    assert out.visual_kb_scope_enabled is False


def test_balanced_profile_enables_ai_edit() -> None:
    s = Settings(visual_pipeline_profile="balanced", visual_use_ai_image_edit=False)
    out = apply_visual_pipeline_profile(s)
    assert out.visual_use_ai_image_edit is True
    assert out.visual_edit_plan_enabled is True
    assert out.visual_kb_scope_enabled is True


def test_fast_profile_disables_edit_plan() -> None:
    s = Settings(visual_pipeline_profile="fast")
    out = apply_visual_pipeline_profile(s)
    assert out.visual_edit_plan_enabled is False
    assert out.visual_smart_routing is True


def test_explicit_env_overrides_profile(monkeypatch) -> None:
    monkeypatch.setenv("VISUAL_USE_AI_IMAGE_EDIT", "false")
    s = Settings(visual_pipeline_profile="balanced", visual_use_ai_image_edit=False)
    out = apply_visual_pipeline_profile(s)
    assert out.visual_use_ai_image_edit is False


def test_pixel_profile() -> None:
    s = Settings(visual_pipeline_profile="pixel")
    out = apply_visual_pipeline_profile(s)
    assert out.visual_produce_mode == "pixel"
    assert out.visual_use_ai_image_edit is False


def test_load_settings_applies_quality_profile(monkeypatch) -> None:
    monkeypatch.delenv("VISUAL_USE_AI_IMAGE_EDIT", raising=False)
    monkeypatch.delenv("VISUAL_PIPELINE_PROFILE", raising=False)
    monkeypatch.delenv("VISUAL_EDIT_PLAN_MODEL", raising=False)
    s = load_settings()
    if os.environ.get("VISUAL_PIPELINE_PROFILE", "quality") == "custom":
        return
    assert s.visual_pipeline_profile == "quality"
    assert s.visual_use_ai_image_edit is True
    assert s.visual_edit_plan_model == "gpt-4o"
