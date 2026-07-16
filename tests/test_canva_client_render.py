"""Test comportamento render Canva (placeholder, senza rete)."""

from __future__ import annotations

from pathlib import Path

from social_automation.canva.client import CanvaClient
from social_automation.models import MediaFormat, Platform


def test_render_placeholder_copies_file(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    src.write_bytes(b"fakejpeg")
    out_dir = tmp_path / "out"
    client = CanvaClient("id", "secret", "http://127.0.0.1:8080/callback", token={})
    out = client.render_for_platform(
        src,
        Platform.INSTAGRAM,
        template_id="DAFX",
        output_dir=out_dir,
        output_stem="stem",
        use_placeholder=True,
    )
    assert out.parent.name == "ig"
    assert out.read_bytes() == b"fakejpeg"
    meta = client.get_last_render_metadata() or {}
    assert meta["mode"] == "placeholder_copy"
    assert meta["template_id"] == "DAFX"
    assert meta["media_format"] == MediaFormat.POST.value


def test_render_placeholder_story_uses_shared_stories_folder(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    src.write_bytes(b"fakejpeg")
    out_dir = tmp_path / "out"
    client = CanvaClient("id", "secret", "http://127.0.0.1:8080/callback", token={})

    out_ig = client.render_for_platform(
        src,
        Platform.INSTAGRAM,
        template_id="DAStory",
        output_dir=out_dir,
        output_stem="stem",
        use_placeholder=True,
        media_format=MediaFormat.STORY,
    )
    out_fb = client.render_for_platform(
        src,
        Platform.FACEBOOK,
        template_id="DAStory",
        output_dir=out_dir,
        output_stem="stem",
        use_placeholder=True,
        media_format=MediaFormat.STORY,
    )

    assert out_ig.parent.name == "stories"
    assert out_fb.parent.name == "stories"
    assert out_ig.parent == out_fb.parent
    assert out_ig != out_fb
    assert "instagram_story" in out_ig.name
    assert "facebook_story" in out_fb.name
    meta = client.get_last_render_metadata() or {}
    assert meta["media_format"] == MediaFormat.STORY.value


def test_render_export_preserves_template_aspect_ratio(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    src.write_bytes(b"fakejpeg")
    out_dir = tmp_path / "out"
    client = CanvaClient("id", "secret", "http://127.0.0.1:8080/callback", token={})

    # Evita rete/Pillow: simuliamo tutta la pipeline remota.
    client.get_first_page_dimensions = lambda _template_id: (1080, 1350)  # type: ignore[method-assign]
    client.upload_image_asset = lambda _image_path: "asset_1"  # type: ignore[method-assign]
    client.create_design_with_asset = (  # type: ignore[method-assign]
        lambda _w, _h, _asset_id, title: "design_1"
    )
    seen: dict[str, int] = {}

    def _fake_export(
        _design_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int = 92,
        pages: list[int] | None = None,
    ) -> bytes:
        del quality, pages
        seen["width"] = int(width or 0)
        seen["height"] = int(height or 0)
        return b"jpeg"

    client.export_jpeg_file = _fake_export  # type: ignore[method-assign]

    out = client.render_for_platform(
        src,
        Platform.INSTAGRAM,
        template_id="DAFX",
        output_dir=out_dir,
        output_stem="stem",
        precrop_cover=False,
    )

    assert out.parent.name == "ig"
    assert out.read_bytes() == b"jpeg"
    assert seen == {"width": 1080, "height": 1350}
    meta = client.get_last_render_metadata() or {}
    assert meta["canvas_width"] == 1080
    assert meta["canvas_height"] == 1350
    assert meta["export_width"] == 1080
    assert meta["export_height"] == 1350


def test_render_story_falls_back_to_vertical_1080x1920(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    src.write_bytes(b"fakejpeg")
    out_dir = tmp_path / "out"
    client = CanvaClient("id", "secret", "http://127.0.0.1:8080/callback", token={})

    client.get_first_page_dimensions = lambda _template_id: None  # type: ignore[method-assign]
    client.upload_image_asset = lambda _image_path: "asset_1"  # type: ignore[method-assign]
    client.create_design_with_asset = (  # type: ignore[method-assign]
        lambda _w, _h, _asset_id, title: "design_1"
    )
    seen: dict[str, int] = {}

    def _fake_export(
        _design_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int = 92,
        pages: list[int] | None = None,
    ) -> bytes:
        del quality, pages
        seen["width"] = int(width or 0)
        seen["height"] = int(height or 0)
        return b"jpeg"

    client.export_jpeg_file = _fake_export  # type: ignore[method-assign]

    out = client.render_for_platform(
        src,
        Platform.FACEBOOK,
        template_id="DAStory",
        output_dir=out_dir,
        output_stem="stem",
        precrop_cover=False,
        media_format=MediaFormat.STORY,
    )

    assert out.parent.name == "stories"
    assert seen == {"width": 1080, "height": 1920}
    meta = client.get_last_render_metadata() or {}
    assert meta["media_format"] == MediaFormat.STORY.value
    assert meta["canvas_width"] == 1080
    assert meta["canvas_height"] == 1920
