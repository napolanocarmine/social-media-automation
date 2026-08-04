from __future__ import annotations

from io import BytesIO

from PIL import Image

from social_automation.models import MediaFormat, Platform
from social_automation.services.upload import validate_upload_bytes, validate_upload_dimensions


def _jpeg_bytes(width: int, height: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def test_validate_upload_dimensions_exact_match() -> None:
    result = validate_upload_dimensions(
        1080,
        1350,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    )
    assert result["valid"] is True
    assert result["expected_width"] == 1080
    assert result["expected_height"] == 1350


def test_validate_upload_dimensions_mismatch() -> None:
    result = validate_upload_dimensions(
        800,
        600,
        platform=Platform.FACEBOOK,
        media_format=MediaFormat.POST,
    )
    assert result["valid"] is False
    assert result["expected_width"] == 1200
    assert result["expected_height"] == 900


def test_validate_upload_bytes_story() -> None:
    data = _jpeg_bytes(1080, 1920)
    result = validate_upload_bytes(
        data,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.STORY,
    )
    assert result["valid"] is True
