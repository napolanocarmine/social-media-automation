"""Applicazione ritocchi leggeri (Pillow) da JSON Story AI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from social_automation.models import MediaFormat, Platform

_LOG = logging.getLogger(__name__)

# Larghezza × altezza
TARGET_SIZE_BY_CROP: dict[str, tuple[int, int]] = {
    "none": (1080, 1080),
    "instagram_4_5": (1080, 1350),
    "instagram_post": (1080, 1350),
    "facebook_post": (1200, 900),
    "facebook_context": (1200, 900),
    "story_9_16": (1080, 1920),
    "instagram_story": (1080, 1920),
}


def crop_mode_for_platform(platform: Platform, media_format: MediaFormat) -> str:
    if media_format == MediaFormat.STORY:
        return "story_9_16"
    if platform == Platform.FACEBOOK:
        return "facebook_context"
    return "instagram_4_5"


# Dimensioni API OpenAI (gpt-image-1.5): solo 1:1, 2:3, 3:2 o auto — niente 4:5 nativo.
# Per IG 4:5 usare 1024x1536 (2:3) + post-crop Pillow (pipeline classica ai_edited).
API_SIZE_BY_CROP: dict[str, str] = {
    "instagram_4_5": "1024x1536",
    "instagram_post": "1024x1536",
    "story_9_16": "1024x1792",
    "instagram_story": "1024x1792",
    "facebook_context": "1536x1024",
    "facebook_post": "1536x1024",
    "none": "auto",
}


def image_api_size_for_crop(crop_mode: str) -> str:
    """Risoluzione API image edit in base al formato social scelto."""
    mode = (crop_mode or "").strip().lower()
    return API_SIZE_BY_CROP.get(mode, API_SIZE_BY_CROP["instagram_4_5"])


def target_aspect_ratio_for_crop(crop_mode: str) -> float:
    """Aspect ratio larghezza/altezza del formato social."""
    tw, th = TARGET_SIZE_BY_CROP.get(
        (crop_mode or "").strip().lower(),
        TARGET_SIZE_BY_CROP["instagram_4_5"],
    )
    return tw / th if th else 1.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _coerce_adjustment_float(value: Any, *, field: str, default: float = 0.0) -> float:
    """Converte un valore di ritocco in float; stringhe non numeriche → default."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            _LOG.warning(
                "light_adjustments.%s non numerico (%r), uso %s",
                field,
                value,
                default,
            )
            return default
    _LOG.warning(
        "light_adjustments.%s tipo non supportato (%r), uso %s",
        field,
        value,
        default,
    )
    return default


def normalize_image_orientation(im: Image.Image) -> Image.Image:
    """Applica orientamento EXIF (foto smartphone) prima di crop/ritocchi."""
    return ImageOps.exif_transpose(im)


def normalize_image_file(path: Path) -> None:
    """Riscrive il file applicando orientamento EXIF (in-place, senza tag EXIF residui)."""
    with Image.open(path) as im:
        out = normalize_image_orientation(im)
        save_fmt = "JPEG"
        if out.mode not in ("RGB", "L"):
            out = out.convert("RGB")
        # Salva pixel già orientati; niente EXIF → evita doppia rotazione nel browser.
        out.save(path, format=save_fmt, quality=92, optimize=True)


def _center_crop_to_aspect(im: Image.Image, target_w: int, target_h: int) -> Image.Image:
    tw, th = max(1, target_w), max(1, target_h)
    target_ratio = tw / th
    w, h = im.size
    src_ratio = w / h
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    return im.crop(box).resize((tw, th), Image.Resampling.LANCZOS)


def apply_adjustments(
    im: Image.Image,
    adjustments: dict[str, Any],
    *,
    fallback_crop: str,
) -> Image.Image:
    """Ritocchi conservativi su RGB."""
    out = normalize_image_orientation(im).convert("RGB")
    crop = str(adjustments.get("crop_mode") or fallback_crop or "none").strip().lower()
    if crop in {"", "none"}:
        crop = fallback_crop
    target = TARGET_SIZE_BY_CROP.get(crop, TARGET_SIZE_BY_CROP["instagram_4_5"])
    out = _center_crop_to_aspect(out, target[0], target[1])

    exposure = _clamp(
        _coerce_adjustment_float(adjustments.get("exposure"), field="exposure"),
        -0.15,
        0.15,
    )
    contrast = _clamp(
        _coerce_adjustment_float(adjustments.get("contrast"), field="contrast"),
        -0.15,
        0.15,
    )
    sharpness = _clamp(
        _coerce_adjustment_float(adjustments.get("sharpness"), field="sharpness"),
        0.0,
        0.3,
    )
    saturation = _clamp(
        _coerce_adjustment_float(adjustments.get("saturation"), field="saturation"),
        -0.1,
        0.1,
    )

    if abs(exposure) > 0.001:
        out = ImageEnhance.Brightness(out).enhance(1.0 + exposure)
    if abs(contrast) > 0.001:
        out = ImageEnhance.Contrast(out).enhance(1.0 + contrast)
    if abs(saturation) > 0.001:
        out = ImageEnhance.Color(out).enhance(1.0 + saturation)
    if sharpness > 0.001:
        out = ImageEnhance.Sharpness(out).enhance(1.0 + sharpness)
        if sharpness > 0.15:
            out = out.filter(ImageFilter.UnsharpMask(radius=1, percent=80, threshold=3))
    return out


def apply_tone_adjustments(
    im: Image.Image,
    adjustments: dict[str, Any],
) -> Image.Image:
    """Solo esposizione/contrasto/saturazione — senza crop né nitidezza."""
    out = normalize_image_orientation(im).convert("RGB")
    exposure = _clamp(
        _coerce_adjustment_float(adjustments.get("exposure"), field="exposure"),
        -0.15,
        0.15,
    )
    contrast = _clamp(
        _coerce_adjustment_float(adjustments.get("contrast"), field="contrast"),
        -0.15,
        0.15,
    )
    saturation = _clamp(
        _coerce_adjustment_float(adjustments.get("saturation"), field="saturation"),
        -0.1,
        0.1,
    )
    if abs(exposure) > 0.001:
        out = ImageEnhance.Brightness(out).enhance(1.0 + exposure)
    if abs(contrast) > 0.001:
        out = ImageEnhance.Contrast(out).enhance(1.0 + contrast)
    if abs(saturation) > 0.001:
        out = ImageEnhance.Color(out).enhance(1.0 + saturation)
    return out


def apply_tone_to_file(
    source: Path,
    dest: Path,
    adjustments: dict[str, Any],
    *,
    jpeg_quality: int = 95,
) -> Path:
    """Applica tono/luce numerico senza crop (post-AI hybrid pipeline)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        out = apply_tone_adjustments(im, adjustments)
        out.save(dest, format="JPEG", quality=jpeg_quality, optimize=True)
    return dest


def apply_retouch_to_file(
    source: Path,
    dest: Path,
    adjustments: dict[str, Any],
    *,
    fallback_crop: str,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        out = apply_adjustments(im, adjustments, fallback_crop=fallback_crop)
        out.save(dest, format="JPEG", quality=92, optimize=True)
    return dest


def approved_from_retouch(data: dict[str, Any]) -> bool:
    vr = data.get("visual_review")
    if isinstance(vr, dict) and "approved" in vr:
        return bool(vr.get("approved"))
    fr = data.get("final_review")
    if isinstance(fr, dict):
        return str(fr.get("status", "")).upper() == "APPROVED"
    return True
