"""Ritaglio stile Canva «Riempi»: scala l'immagine per coprire il rettangolo e centra il crop."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def write_cover_jpeg(
    src: Path,
    dest: Path,
    target_width: int,
    target_height: int,
    *,
    jpeg_quality: int = 92,
) -> None:
    """Ridimensiona con aspect ratio preservato (cover) e ritaglia al centro → JPEG esatto WxH."""
    tw = max(1, int(target_width))
    th = max(1, int(target_height))
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        sw, sh = im.size
        if sw < 1 or sh < 1:
            raise ValueError("Immagine sorgente con dimensioni non valide")
        scale = max(tw / sw, th / sh)
        nw = max(1, int(round(sw * scale)))
        nh = max(1, int(round(sh * scale)))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - tw) // 2
        top = (nh - th) // 2
        im = im.crop((left, top, left + tw, top + th))
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=jpeg_quality, optimize=True)
