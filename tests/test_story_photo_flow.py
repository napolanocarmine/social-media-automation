from __future__ import annotations

from pathlib import Path

from PIL import Image

from social_automation.brand.copy_pack import caption_for_platform, copy_approved, planning_detail_with_caption
from social_automation.models import MediaFormat, Platform
from social_automation.processing.image_adjust import apply_adjustments, crop_mode_for_platform


def test_crop_mode_for_platform() -> None:
    assert crop_mode_for_platform(Platform.INSTAGRAM, MediaFormat.POST) == "instagram_4_5"
    assert crop_mode_for_platform(Platform.FACEBOOK, MediaFormat.POST) == "facebook_context"
    assert crop_mode_for_platform(Platform.INSTAGRAM, MediaFormat.STORY) == "story_9_16"


def test_apply_adjustments_resizes(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    im = Image.new("RGB", (2000, 1500), color=(120, 80, 40))
    im.save(src, format="JPEG")
    with Image.open(src) as opened:
        out = apply_adjustments(
            opened,
            {"crop_mode": "instagram_4_5", "exposure": 0.05, "sharpness": 0.1},
            fallback_crop="instagram_4_5",
        )
    assert out.size == (1080, 1350)


def test_apply_adjustments_ignores_non_numeric_strings(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    im = Image.new("RGB", (800, 600), color=(100, 100, 100))
    im.save(src, format="JPEG")
    with Image.open(src) as opened:
        out = apply_adjustments(
            opened,
            {
                "crop_mode": "instagram_4_5",
                "exposure": "Increase exposure slightly to brighten the overall image.",
                "contrast": 0.0,
            },
            fallback_crop="instagram_4_5",
        )
    assert out.size == (1080, 1350)


def test_caption_for_platform_includes_hashtags() -> None:
    data = {
        "instagram_caption": "Serata al banco.",
        "hashtags": ["#TuttaNataStory", "#Story"],
    }
    cap = caption_for_platform(data, platform=Platform.INSTAGRAM, media_format=MediaFormat.POST)
    assert "Serata al banco." in cap
    assert "#TuttaNataStory" in cap


def test_copy_approved() -> None:
    assert copy_approved({"final_review": {"status": "APPROVED"}})
    assert not copy_approved({"final_review": {"status": "REVISION_REQUIRED"}})


def test_planning_detail_json() -> None:
    raw = planning_detail_with_caption("Ciao Story")
    assert '"caption"' in raw
    assert "Ciao Story" in raw
