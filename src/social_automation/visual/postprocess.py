"""Post-processing immagini dopo edit AI (crop intelligente vs solo resize)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image

from social_automation.processing.image_adjust import (
    TARGET_SIZE_BY_CROP,
    normalize_image_orientation,
    target_aspect_ratio_for_crop,
)

_LOG = logging.getLogger(__name__)

DEFAULT_JPEG_EXPORT_QUALITY = 95


def target_size_for_crop(crop_mode: str) -> tuple[int, int]:
    mode = (crop_mode or "").strip().lower()
    return TARGET_SIZE_BY_CROP.get(mode, TARGET_SIZE_BY_CROP["instagram_4_5"])


def _center_crop_to_aspect_ratio(im: Image.Image, target_ratio: float) -> Image.Image:
    """Ritaglia al ratio target senza ridimensionare (solo composizione)."""
    w, h = im.size
    if h <= 0:
        return im
    src_ratio = w / h
    if abs(src_ratio - target_ratio) < 1e-6:
        return im
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        return im.crop((left, 0, left + new_w, h))
    new_h = int(w / target_ratio)
    top = (h - new_h) // 2
    return im.crop((0, top, w, top + new_h))


def _center_crop_to_aspect(im: Image.Image, target_w: int, target_h: int) -> Image.Image:
    tw, th = max(1, target_w), max(1, target_h)
    target_ratio = tw / th
    cropped = _center_crop_to_aspect_ratio(im, target_ratio)
    return cropped.resize((tw, th), Image.Resampling.LANCZOS)


def _maybe_downscale(im: Image.Image, *, max_edge: int) -> Image.Image:
    w, h = im.size
    edge = max(w, h)
    if edge <= max_edge:
        return im
    scale = max_edge / edge
    return im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)


def precrop_source_for_api(
    source: Path,
    dest: Path,
    crop_mode: str,
    *,
    aspect_tolerance: float = 0.025,
    max_edge: int = 2048,
    jpeg_quality: int = DEFAULT_JPEG_EXPORT_QUALITY,
) -> Path:
    """
    Pre-crop deterministico al formato social prima dell'edit AI.

    L'API gpt-image-1.5 non supporta 4:5 nativo: crop qui, edit AI solo su tono/luce.
    Il center crop non altera esposizione o bilanciamento del bianco — solo inquadratura.
    """
    target_ratio = target_aspect_ratio_for_crop(crop_mode)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        rgb = normalize_image_orientation(im).convert("RGB")
        w, h = rgb.size
        actual_ratio = w / h if h else target_ratio
        ratio_delta = abs(actual_ratio - target_ratio) / target_ratio
        if ratio_delta <= aspect_tolerance:
            out = _maybe_downscale(rgb, max_edge=max_edge)
            _LOG.info(
                "Pre-crop skipped (ratio già %.3f per %s), max_edge=%s",
                actual_ratio,
                crop_mode,
                max(out.size),
            )
        else:
            out = _center_crop_to_aspect_ratio(rgb, target_ratio)
            out = _maybe_downscale(out, max_edge=max_edge)
            _LOG.info(
                "Pre-crop applicato per %s: %sx%s → %sx%s (solo composizione)",
                crop_mode,
                w,
                h,
                out.size[0],
                out.size[1],
            )
        out.save(dest, format="JPEG", quality=jpeg_quality, optimize=True)
    return dest


def finalize_image_for_crop_mode(
    source: Path,
    dest: Path,
    crop_mode: str,
    *,
    aspect_tolerance: float = 0.025,
    jpeg_quality: int = DEFAULT_JPEG_EXPORT_QUALITY,
) -> Path:
    """
    Normalizza dimensioni per il formato social.

    Se l'aspect ratio è già corretto, applica solo resize (nessun center crop).
    Il center crop altera l'inquadratura, non luci/colori; il resize può ridurre
    leggermente la nitidezza percepita.
    """
    target_w, target_h = target_size_for_crop(crop_mode)
    target_ratio = target_w / target_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        rgb = normalize_image_orientation(im).convert("RGB")
        w, h = rgb.size
        actual_ratio = w / h if h else target_ratio
        ratio_delta = abs(actual_ratio - target_ratio) / target_ratio
        if ratio_delta <= aspect_tolerance:
            out = rgb.resize((target_w, target_h), Image.Resampling.LANCZOS)
            _LOG.info(
                "Post-process resize only %s: %sx%s → %sx%s",
                crop_mode,
                w,
                h,
                target_w,
                target_h,
            )
        else:
            out = _center_crop_to_aspect(rgb, target_w, target_h)
            _LOG.warning(
                "Post-process center crop %s: API %sx%s (ratio %.3f) → %sx%s "
                "(composizione; non modifica esposizione/colori)",
                crop_mode,
                w,
                h,
                actual_ratio,
                target_w,
                target_h,
            )
        out.save(dest, format="JPEG", quality=jpeg_quality, optimize=True)
    return dest


def copy_or_finalize_for_crop_mode(
    source: Path,
    dest: Path,
    crop_mode: str,
    *,
    jpeg_quality: int = DEFAULT_JPEG_EXPORT_QUALITY,
) -> Path:
    """Se il file è già alle dimensioni finali, copia senza ricodificare."""
    target_w, target_h = target_size_for_crop(crop_mode)
    with Image.open(source) as im:
        if im.size == (target_w, target_h):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            _LOG.info("Post-process copy (già %sx%s)", target_w, target_h)
            return dest
    return finalize_image_for_crop_mode(
        source,
        dest,
        crop_mode,
        jpeg_quality=jpeg_quality,
    )
