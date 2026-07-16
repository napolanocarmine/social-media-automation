from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual import producer as vp
from social_automation.visual.models import ImageEditApiResult, ImageEditPlan
from social_automation.visual.prompts import build_image_edit_user_prompt, format_edit_plan_for_prompt


def _write_test_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), color=(100, 80, 60)).save(path, format="JPEG")


def test_format_edit_plan_includes_crop_and_steps() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["hamburger", "patatine"],
            "preserve_elements": ["bandierina"],
            "crop_plan": "Patatine visibili a destra.",
            "sharpness_targets": ["hamburger"],
            "preserve_soft_background": True,
            "adjustments_notes": "+0.2 EV",
        }
    )
    text = format_edit_plan_for_prompt(
        plan,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    )
    assert "Patatine visibili a destra" in text
    assert "Nitidezza selettiva su: hamburger" in text
    assert "Esegui in ordine:" in text
    assert "7. Export finale" in text


def test_build_image_edit_user_prompt_uses_plan_subjects() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["persona", "cibo"],
            "sharpness_targets": ["volto", "cibo"],
            "crop_plan": "Mantieni testa e mani visibili.",
        }
    )
    prompt = build_image_edit_user_prompt(
        review={},
        business_category="food",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        content_pillar="food",
        settings=Settings(visual_edit_include_kb=False, visual_hybrid_tone_pipeline=False),
        edit_plan=plan,
        hybrid_mode=False,
    )
    assert "volto e cibo" in prompt
    assert "Piano editing per questa foto" in prompt
    assert "Mantieni testa e mani visibili" in prompt


def test_produce_calls_edit_plan_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "photo.jpg"
    _write_test_jpeg(source)
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_review_enabled=False,
        visual_use_ai_image_edit=True,
        visual_disable_pillow_retouch=True,
        visual_edit_plan_enabled=True,
        visual_hybrid_tone_pipeline=False,
        visual_edit_prompt_compiler=False,
        visual_gpt_pure_mode=False,
        visual_skip_post_crop=True,
        visual_responses_model="gpt-5.5",
        output_dir=tmp_path / "output",
        db_path=tmp_path / "test.db",
    )
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["hamburger"],
            "crop_plan": "Centra il burger.",
            "sharpness_targets": ["hamburger"],
        }
    )
    monkeypatch.setattr(vp, "run_image_edit_plan", lambda *a, **k: plan)

    captured: dict = {}

    def _fake_edit(src, *, instructions, user_prompt, legacy_prompt, dest_path, settings, crop_mode, **kwargs):
        captured["user_prompt"] = user_prompt
        _write_test_jpeg(dest_path)
        return ImageEditApiResult(path=dest_path)

    monkeypatch.setattr(vp, "run_image_edit", _fake_edit)

    result = vp.produce_final_asset(
        source,
        settings=settings,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        file_id="abc",
    )

    assert result.method == "ai_edited"
    assert result.edit_plan_json is not None
    assert "Centra il burger" in captured["user_prompt"]
