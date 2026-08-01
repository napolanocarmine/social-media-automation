from __future__ import annotations

from pathlib import Path

from PIL import Image

from social_automation.visual.postprocess import (
    finalize_image_for_crop_mode,
    resize_only_to_target_size,
)


def test_resize_only_story_scales_when_ratio_matches(tmp_path: Path) -> None:
    src = tmp_path / "ai.jpg"
    dest = tmp_path / "out.jpg"
    Image.new("RGB", (720, 1280), color=(40, 80, 120)).save(src, format="JPEG")
    out = resize_only_to_target_size(src, dest, "story_9_16")
    assert out == dest
    with Image.open(dest) as im:
        assert im.size == (1080, 1920)


def test_resize_only_story_skips_center_crop_on_wrong_ratio(tmp_path: Path) -> None:
    src = tmp_path / "ai.jpg"
    dest = tmp_path / "out.jpg"
    Image.new("RGB", (1200, 900), color=(40, 80, 120)).save(src, format="JPEG")
    out = resize_only_to_target_size(src, dest, "story_9_16")
    assert out == dest
    with Image.open(dest) as im:
        assert im.size == (1200, 900)


def test_finalize_story_disables_center_crop(tmp_path: Path) -> None:
    src = tmp_path / "ai.jpg"
    dest = tmp_path / "out.jpg"
    Image.new("RGB", (1200, 900), color=(40, 80, 120)).save(src, format="JPEG")
    out = finalize_image_for_crop_mode(
        src,
        dest,
        "story_9_16",
        allow_center_crop=False,
    )
    assert out == dest
    with Image.open(dest) as im:
        assert im.size == (1200, 900)
