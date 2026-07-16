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
    Image.new("RGB", (1200, 800), color=(180, 90, 40)).save(path, format="JPEG")


def test_gpt_direct_always_runs_ai_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "drive" / "photo.jpg"
    _write_test_jpeg(source)
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_review_enabled=False,
        visual_use_ai_image_edit=True,
        visual_disable_pillow_retouch=True,
        visual_hybrid_tone_pipeline=False,
        visual_edit_prompt_compiler=False,
        visual_edit_plan_enabled=False,
        visual_gpt_pure_mode=False,
        visual_skip_post_crop=True,
        visual_responses_model="gpt-5.5",
        output_dir=tmp_path / "output",
        db_path=tmp_path / "test.db",
    )
    review_called = MagicMock(side_effect=AssertionError("visual review must not run"))
    monkeypatch.setattr(vp, "run_visual_review", review_called)

    def _fake_edit(src, *, instructions, user_prompt, legacy_prompt, dest_path, settings, crop_mode, **kwargs):
        assert crop_mode == "instagram_4_5"
        assert "Story non vende" in instructions or instructions == ""
        assert "EDIT the attached photograph" in user_prompt
        assert "Image Editing Task" in user_prompt
        _write_test_jpeg(dest_path)
        return ImageEditApiResult(path=dest_path)

    monkeypatch.setattr(vp, "run_image_edit", _fake_edit)

    result = vp.produce_final_asset(
        source,
        settings=settings,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        file_id="abc123",
    )

    review_called.assert_not_called()
    assert result.method == "ai_edited"
    assert Path(result.final_path).is_file()
    assert result.generated_image_path is None


def test_visual_review_legacy_path_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from social_automation.visual.models import VisualReview

    source = tmp_path / "photo.jpg"
    _write_test_jpeg(source)
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_review_enabled=True,
        visual_use_ai_image_edit=True,
        output_dir=tmp_path / "output",
        db_path=tmp_path / "test.db",
    )
    review = VisualReview(
        score=9.5,
        approved=True,
        needs_editing=False,
        reasoning="Alta qualità",
        suggested_format="instagram_4_5",
    )
    monkeypatch.setattr(vp, "run_visual_review", lambda *a, **k: review)
    ai_edit = MagicMock(side_effect=AssertionError("generative edit must not run"))
    monkeypatch.setattr(vp, "run_image_edit", ai_edit)

    result = vp.produce_final_asset(
        source,
        settings=settings,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        file_id="abc123",
    )

    assert result.method == "original"
    ai_edit.assert_not_called()


def test_gpt_direct_edit_failure_raises_without_pillow_fallback(
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
        visual_responses_model="gpt-5.5",
        output_dir=tmp_path / "output",
        db_path=tmp_path / "test.db",
    )

    def _fail_edit(*args, **kwargs):
        raise RuntimeError("blocked by proxy")

    monkeypatch.setattr(vp, "run_image_edit", _fail_edit)
    pillow = MagicMock(side_effect=AssertionError("pillow"))
    monkeypatch.setattr(vp, "run_retouch_analysis", pillow)

    with pytest.raises(RuntimeError, match="Image edit AI fallito"):
        vp.produce_final_asset(
            source,
            settings=settings,
            platform=Platform.INSTAGRAM,
            media_format=MediaFormat.POST,
            business_category="food",
            file_id="x",
        )
    pillow.assert_not_called()
