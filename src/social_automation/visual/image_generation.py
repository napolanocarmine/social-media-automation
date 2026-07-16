"""Chiamate API image editing (OpenAI Images)."""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

import httpx
from PIL import Image

from social_automation.http.vision_httpx import vision_httpx_tls_params
from social_automation.processing.image_adjust import image_api_size_for_crop
from social_automation.settings import Settings

_LOG = logging.getLogger(__name__)


def image_edit_configured(settings: Settings) -> bool:
    return bool(
        (settings.vision_api_key or "").strip()
        and (settings.visual_image_model or "").strip()
    )


def _api_base(settings: Settings) -> str:
    return (settings.vision_api_base_url or "https://api.openai.com/v1").rstrip("/")


def _prepare_edit_bytes(source_path: Path) -> tuple[bytes, str, str]:
    """Converte in PNG RGB per compatibilità API edit."""
    with Image.open(source_path) as im:
        rgb = im.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="PNG")
        return buf.getvalue(), "image.png", "image/png"


def _edit_request_data(settings: Settings, *, prompt: str, crop_mode: str = "instagram_4_5") -> dict[str, str]:
    model = settings.visual_image_model.strip()
    data: dict[str, str] = {
        "model": model,
        "prompt": prompt.strip(),
        "n": "1",
    }
    explicit = (settings.visual_image_size or "").strip()
    if explicit:
        data["size"] = explicit
    elif model.startswith("gpt-image"):
        data["size"] = image_api_size_for_crop(crop_mode)

    fidelity = (settings.visual_image_input_fidelity or "").strip().lower()
    if fidelity in {"high", "low"} and model.startswith("gpt-image"):
        data["input_fidelity"] = fidelity

    quality = (settings.visual_image_quality or "").strip().lower()
    if quality in {"high", "medium", "low"} and model.startswith("gpt-image"):
        data["quality"] = quality

    if model.startswith("gpt-image"):
        data["output_format"] = "jpeg"

    return data


def edit_image_with_prompt(
    source_path: Path,
    *,
    prompt: str,
    dest_path: Path,
    settings: Settings,
    crop_mode: str = "instagram_4_5",
    jpeg_quality: int = 95,
) -> Path:
    """
    Modifica immagine via OpenAI Images API (``/images/edits``).
    Salva il risultato in ``dest_path`` (JPEG).
    """
    if not image_edit_configured(settings):
        raise RuntimeError("Visual image model non configurato (VISUAL_IMAGE_MODEL)")
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    png_bytes, filename, mime = _prepare_edit_bytes(source_path)
    url = f"{_api_base(settings)}/images/edits"
    headers = {"Authorization": f"Bearer {settings.vision_api_key.strip()}"}

    files = {"image": (filename, png_bytes, mime)}
    data = _edit_request_data(settings, prompt=prompt, crop_mode=crop_mode)

    tls = vision_httpx_tls_params(settings)
    with httpx.Client(
        timeout=180.0,
        verify=tls["verify"],
        trust_env=tls["trust_env"],
    ) as client:
        resp = client.post(url, headers=headers, data=data, files=files)
    if resp.status_code >= 400:
        raise RuntimeError(f"Image edit API {resp.status_code}: {resp.text[:500]}")

    body = resp.json()
    items = body.get("data") or []
    if not items:
        raise RuntimeError("Image edit API: risposta senza data")

    item = items[0]
    raw: bytes | None = None
    if item.get("b64_json"):
        raw = base64.standard_b64decode(str(item["b64_json"]))
    elif item.get("url"):
        with httpx.Client(
            timeout=120.0,
            verify=tls["verify"],
            trust_env=tls["trust_env"],
        ) as client:
            r = client.get(str(item["url"]))
            r.raise_for_status()
            raw = r.content
    if not raw:
        raise RuntimeError("Image edit API: nessun payload immagine")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(raw)) as out_im:
        out_im.convert("RGB").save(
            dest_path, format="JPEG", quality=jpeg_quality, optimize=True
        )
    return dest_path
