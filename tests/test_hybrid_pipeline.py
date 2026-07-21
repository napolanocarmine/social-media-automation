from __future__ import annotations

from pathlib import Path

from PIL import Image

from social_automation.models import MediaFormat, Platform
from social_automation.processing.image_adjust import apply_tone_to_file
from social_automation.settings import Settings
from social_automation.visual import producer as vp
from social_automation.visual.models import ImageEditPlan, LightAdjustments
from social_automation.visual.prompts import (
    build_image_edit_user_prompt,
    format_edit_plan_for_prompt,
)


def test_light_adjustments_from_dict() -> None:
    la = LightAdjustments.from_dict(
        {"exposure": 0.08, "contrast": 0.04, "saturation": 0.0, "sharpness": 0.0}
    )
    assert la.exposure == 0.08
    assert la.has_tone is True
    assert la.has_any is True


def test_image_edit_plan_nested_light_adjustments() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["hamburger"],
            "light_adjustments": {"exposure": 0.1, "contrast": 0.03},
        }
    )
    assert plan.light_adjustments.exposure == 0.1
    assert plan.has_content is True
    assert "light_adjustments" in plan.to_dict()


def test_format_edit_plan_hybrid_mode() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["hamburger"],
            "sharpness_targets": ["hamburger"],
            "light_adjustments": {"exposure": 0.08},
        }
    )
    text = format_edit_plan_for_prompt(
        plan,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        hybrid_mode=True,
    )
    assert "già applicato" in text
    assert "Nitidezza selettiva" in text
    assert "applicati in post" in text
    assert "Crop al formato" not in text


def test_hybrid_prompt_excludes_global_exposure() -> None:
    prompt = build_image_edit_user_prompt(
        review={},
        business_category="food",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        content_pillar="food",
        settings=Settings(visual_edit_include_kb=False),
        hybrid_mode=True,
    )
    assert "NON fare" in prompt or "NON fare (già gestito" in prompt
    assert "nessun aumento globale di esposizione" in prompt


def test_apply_tone_to_file(tmp_path: Path) -> None:
    source = tmp_path / "in.jpg"
    dest = tmp_path / "out.jpg"
    Image.new("RGB", (100, 100), color=(80, 80, 80)).save(source, format="JPEG")
    apply_tone_to_file(
        source,
        dest,
        {"exposure": 0.1, "contrast": 0.05, "saturation": 0.0},
        jpeg_quality=95,
    )
    assert dest.is_file()


def test_effective_tone_defaults() -> None:
    plan = ImageEditPlan.from_dict({"subjects": ["cibo"]})
    tone = vp._effective_tone_adjustments(plan, hybrid=True)
    assert tone is not None
    assert tone["exposure"] == 0.08


def test_effective_tone_from_plan() -> None:
    plan = ImageEditPlan.from_dict(
        {"light_adjustments": {"exposure": 0.11, "contrast": 0.02}}
    )
    tone = vp._effective_tone_adjustments(plan, hybrid=True)
    assert tone is not None
    assert tone["exposure"] == 0.11
