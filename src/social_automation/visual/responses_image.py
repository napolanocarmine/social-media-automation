"""Image edit via OpenAI Responses API (come ChatGPT custom GPT /produce)."""

from __future__ import annotations

import hashlib
import base64
import io
import logging
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from social_automation.brand.openai_json import _encode_image
from social_automation.http.vision_httpx import vision_httpx_tls_params
from social_automation.processing.image_adjust import image_api_size_for_crop
from social_automation.settings import Settings
from social_automation.visual.models import ImageEditApiResult

_LOG = logging.getLogger(__name__)


def responses_image_configured(settings: Settings) -> bool:
    return bool(
        (settings.vision_api_key or "").strip()
        and (settings.visual_responses_model or "").strip()
    )


def _api_base(settings: Settings) -> str:
    return (settings.vision_api_base_url or "https://api.openai.com/v1").rstrip("/")


def _resolve_api_size(settings: Settings, crop_mode: str) -> str:
    explicit = (settings.visual_image_size or "").strip()
    if explicit:
        return explicit
    return image_api_size_for_crop(crop_mode)


def _image_generation_tool(settings: Settings, *, crop_mode: str) -> dict[str, Any]:
    """
    Tool ``image_generation`` per Responses API.

    gpt-image-2 (default API) rigenera loghi/testi. Per preservarli usare
    gpt-image-1.5 + ``input_fidelity=high`` (come raccomandato da OpenAI per volti/loghi).
    """
    image_model = (settings.visual_responses_image_model or "gpt-image-1.5").strip()
    tool: dict[str, Any] = {
        "type": "image_generation",
        "model": image_model,
        "action": "edit",
    }
    fidelity = (settings.visual_image_input_fidelity or "high").strip().lower()
    if image_model.startswith("gpt-image-1") and fidelity in {"high", "low"}:
        tool["input_fidelity"] = fidelity
    quality = (settings.visual_image_quality or "").strip().lower()
    if quality in {"high", "medium", "low"}:
        tool["quality"] = quality
    tool["size"] = _resolve_api_size(settings, crop_mode)
    tool["output_format"] = "jpeg"
    return tool


def _extract_image_generation_call(body: dict[str, Any]) -> tuple[str, str | None]:
    """Estrae result base64 e revised_prompt dal output Responses API."""
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_generation_call":
            continue
        if item.get("status") == "failed":
            raise RuntimeError(f"Image generation failed: {item}")
        result = item.get("result")
        if not isinstance(result, str) or not result.strip():
            continue
        revised = item.get("revised_prompt")
        revised_text = revised.strip() if isinstance(revised, str) and revised.strip() else None
        return result.strip(), revised_text
    raise RuntimeError("Responses API: nessuna image_generation_call con result")


def _extract_image_b64(body: dict[str, Any]) -> str:
    payload, _ = _extract_image_generation_call(body)
    return payload


def _log_edit_payload_debug(
    settings: Settings,
    *,
    instructions: str,
    user_prompt: str,
    tool: dict[str, Any],
    crop_mode: str,
) -> None:
    if not settings.visual_edit_debug_log:
        return
    prompt_hash = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:16]
    _LOG.info(
        "Image edit debug crop=%s instructions_len=%s user_prompt_len=%s "
        "user_prompt_sha=%s tool=%s",
        crop_mode,
        len(instructions.strip()),
        len(user_prompt.strip()),
        prompt_hash,
        {k: tool.get(k) for k in ("action", "model", "size", "quality", "input_fidelity")},
    )


def edit_image_via_responses(
    source_path: Path,
    *,
    instructions: str,
    user_prompt: str,
    dest_path: Path,
    settings: Settings,
    crop_mode: str = "instagram_4_5",
    jpeg_quality: int = 95,
) -> ImageEditApiResult:
    """
    Modifica immagine come ChatGPT: system (KB) + /produce + foto in input.

    Usa ``POST /v1/responses`` con tool ``image_generation`` e ``action=edit``.
    """
    if not responses_image_configured(settings):
        raise RuntimeError(
            "Responses image edit non configurato (VISION_API_KEY e VISUAL_RESPONSES_MODEL)"
        )
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    api_size = _resolve_api_size(settings, crop_mode)
    tool = _image_generation_tool(settings, crop_mode=crop_mode)
    payload: dict[str, Any] = {
        "model": settings.visual_responses_model.strip(),
        "tool_choice": {"type": "image_generation"},
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt.strip()},
                    {
                        "type": "input_image",
                        "detail": "original",
                        "image_url": _encode_image(source_path),
                    },
                ],
            }
        ],
        "tools": [tool],
    }
    if instructions.strip():
        payload["instructions"] = instructions.strip()

    _log_edit_payload_debug(
        settings,
        instructions=instructions,
        user_prompt=user_prompt,
        tool=tool,
        crop_mode=crop_mode,
    )
    url = f"{_api_base(settings)}/responses"
    headers = {
        "Authorization": f"Bearer {settings.vision_api_key.strip()}",
        "Content-Type": "application/json",
    }
    tls = vision_httpx_tls_params(settings)
    with httpx.Client(
        timeout=300.0,
        verify=tls["verify"],
        trust_env=tls["trust_env"],
    ) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"Responses API {resp.status_code}: {resp.text[:800]}")

    body = resp.json()
    raw_b64, revised_prompt = _extract_image_generation_call(body)
    raw = base64.standard_b64decode(raw_b64)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(raw)) as out_im:
        out_im.convert("RGB").save(
            dest_path, format="JPEG", quality=jpeg_quality, optimize=True
        )
    if revised_prompt:
        preview = revised_prompt[:240].replace("\n", " ")
        _LOG.info(
            "Image edit revised_prompt (%s chars): %s%s",
            len(revised_prompt),
            preview,
            "…" if len(revised_prompt) > 240 else "",
        )
    else:
        _LOG.info("Image edit revised_prompt: (non restituito dall'API)")
    _LOG.info(
        "Image edit via Responses API mainline=%s image_model=%s crop=%s size=%s",
        settings.visual_responses_model.strip(),
        (settings.visual_responses_image_model or "gpt-image-1.5").strip(),
        crop_mode,
        api_size,
    )
    return ImageEditApiResult(path=dest_path, revised_prompt=revised_prompt)
