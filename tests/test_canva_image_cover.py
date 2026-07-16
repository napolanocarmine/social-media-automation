"""Test ritaglio cover (stile Riempi)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from social_automation.canva.image_cover import write_cover_jpeg


def test_write_cover_jpeg_landscape_to_square(tmp_path: Path) -> None:
    src = tmp_path / "wide.png"
    dest = tmp_path / "out.jpg"
    Image.new("RGB", (400, 200), color=(255, 0, 0)).save(src)
    write_cover_jpeg(src, dest, 100, 100)
    with Image.open(dest) as out:
        assert out.size == (100, 100)
