from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual import producer as vp
from social_automation.visual.models import ImageEditApiResult


def _write_test_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), color=(100, 80, 60)).save(path, format="JPEG")


def test_gpt_pure_mode_skips_precrop_and_hybrid(
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
        visual_gpt_pure_mode=True,
        visual_edit_plan_enabled=True,
        visual_hybrid_tone_pipeline=True,
        visual_precrop_before_api=True,
        visual_edit_prompt_compiler=True,
        visual_responses_model="gpt-5.5",
        output_dir=tmp_path / "output",
        db_path=tmp_path / "test.db",
    )

    plan_called = MagicMock(side_effect=AssertionError("edit plan must not run in pure mode"))
    monkeypatch.setattr(vp, "run_image_edit_plan", plan_called)
    precrop_called = MagicMock(side_effect=AssertionError("precrop must not run in pure mode"))
    monkeypatch.setattr(vp, "precrop_source_for_api", precrop_called)
    compiler_called = MagicMock(side_effect=AssertionError("compiler must not run in pure mode"))
    monkeypatch.setattr(vp, "compile_image_edit_prompt", compiler_called)

    captured: dict = {}

    def _fake_edit(src, *, instructions, user_prompt, legacy_prompt, dest_path, settings, crop_mode, **kwargs):
        captured["src"] = src
        captured["user_prompt"] = user_prompt
        _write_test_jpeg(dest_path)
        return ImageEditApiResult(
            path=dest_path,
            revised_prompt="Revised: subtle food photo edit",
        )

    monkeypatch.setattr(vp, "run_image_edit", _fake_edit)

    result = vp.produce_final_asset(
        source,
        settings=settings,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        file_id="pure1",
    )

    plan_called.assert_not_called()
    precrop_called.assert_not_called()
    compiler_called.assert_not_called()
    assert captured["src"] == source
    assert "pipeline ibrida" not in captured["user_prompt"]
    assert result.method == "ai_edited_pure"
    assert result.edit_plan_json is not None
    assert result.edit_plan_json.get("mode") == "gpt_pure"
    assert "Revised:" in (result.edit_plan_json.get("revised_prompt") or "")


def test_extract_image_generation_call_reads_revised_prompt() -> None:
    from social_automation.visual.responses_image import _extract_image_generation_call

    b64, revised = _extract_image_generation_call(
        {
            "output": [
                {
                    "type": "image_generation_call",
                    "status": "completed",
                    "result": "abc123",
                    "revised_prompt": " sharpen the burger ",
                }
            ]
        }
    )
    assert b64 == "abc123"
    assert revised == "sharpen the burger"
