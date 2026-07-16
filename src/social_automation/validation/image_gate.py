"""Gate di validazione immagine (LLM vision + eventuali check deterministici)."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path

import httpx

from social_automation.http.vision_httpx import vision_httpx_tls_params
from social_automation.models import Platform, ValidationResult
from social_automation.settings import Settings
from social_automation.validation.vision_brand import load_vision_brand_instructions

_LOG = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{[^{}]*\"pass\"[^{}]*\}", re.DOTALL)


def vision_validation_configured(*, api_key: str, model: str) -> bool:
    return bool((api_key or "").strip() and (model or "").strip())


def _encode_image_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    mime = mime or "image/jpeg"
    raw = image_path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _parse_vision_json(text: str) -> tuple[bool, str]:
    text = (text or "").strip()
    if not text:
        return False, "Risposta vision vuota"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if not match:
            return False, f"Risposta vision non JSON: {text[:200]}"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return False, f"Risposta vision non interpretabile: {text[:200]}"
    if not isinstance(data, dict):
        return False, "Risposta vision non è un oggetto JSON"
    passed = bool(data.get("pass"))
    reason = str(data.get("reason") or ("OK" if passed else "Non approvata")).strip()
    return passed, reason


def validate_image_for_publish(
    image_path: Path,
    platform: Platform,
    *,
    api_key: str,
    model: str,
    extra_instructions: str | None = None,
    api_base_url: str = "",
    business_category: str | None = None,
    timeout_s: float = 60.0,
    settings: Settings | None = None,
) -> ValidationResult:
    """Gate vision brand tramite API OpenAI-compatible (chat completions + immagine)."""
    _ = platform
    if not vision_validation_configured(api_key=api_key, model=model):
        return ValidationResult(
            True,
            reason="Validazione vision disattivata (VISION_API_KEY o VISION_MODEL vuoti).",
        )
    if not image_path.is_file():
        return ValidationResult(False, reason=f"File immagine assente: {image_path}")

    instructions = (extra_instructions or "").strip() or load_vision_brand_instructions(
        category=business_category
    )
    data_url = _encode_image_data_url(image_path)
    base = (api_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": model.strip(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instructions},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 300,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        tls = vision_httpx_tls_params(settings)
        with httpx.Client(
            timeout=timeout_s,
            verify=tls["verify"],
            trust_env=tls["trust_env"],
        ) as client:
            resp = client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            return ValidationResult(
                False,
                reason=f"Vision API HTTP {resp.status_code}: {resp.text[:300]}",
            )
        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            return ValidationResult(False, reason="Vision API: risposta senza choices")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            parts = [str(p.get("text", "")) for p in content if isinstance(p, dict)]
            content = "\n".join(parts)
        passed, reason = _parse_vision_json(str(content))
        return ValidationResult(passed, reason=reason, raw_response=body)
    except httpx.HTTPError as exc:
        _LOG.warning("Vision validation HTTP error: %s", exc)
        return ValidationResult(False, reason=f"Errore rete vision: {exc}")
    except Exception as exc:  # pragma: no cover - difesa
        _LOG.warning("Vision validation error: %s", exc)
        return ValidationResult(False, reason=f"Errore vision: {exc}")
