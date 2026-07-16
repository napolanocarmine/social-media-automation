"""Chiamate OpenAI-compatible con risposta JSON."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from social_automation.http.vision_httpx import vision_httpx_tls_params
from social_automation.settings import Settings

_LOG = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def api_configured(*, api_key: str, model: str) -> bool:
    return bool((api_key or "").strip() and (model or "").strip())


def _encode_image(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/jpeg"
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Risposta vuota")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise ValueError(f"JSON non trovato: {text[:300]}") from None
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Risposta non è un oggetto JSON")
    return data


def chat_vision_json(
    *,
    image_path: Path,
    system_message: str,
    user_prompt: str,
    api_key: str,
    model: str,
    api_base_url: str = "",
    max_tokens: int = 1200,
    timeout_s: float = 120.0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Vision + testo → dict JSON parsato."""
    if not image_path.is_file():
        raise FileNotFoundError(str(image_path))
    base = (api_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    messages: list[dict[str, Any]] = []
    if system_message.strip():
        messages.append({"role": "system", "content": system_message.strip()})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": _encode_image(image_path)}},
            ],
        }
    )
    payload: dict[str, Any] = {
        "model": model.strip(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    # OpenAI nativo: forza oggetto JSON (riduce risposte mal formattate).
    if not api_base_url.strip() or "openai.com" in base:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    tls = vision_httpx_tls_params(settings)
    with httpx.Client(
        timeout=timeout_s,
        verify=tls["verify"],
        trust_env=tls["trust_env"],
    ) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI: risposta senza choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return parse_json_object(str(content))


def chat_text(
    *,
    system_message: str,
    user_prompt: str,
    api_key: str,
    model: str,
    api_base_url: str = "",
    max_tokens: int = 2000,
    timeout_s: float = 120.0,
    settings: Settings | None = None,
) -> str:
    """Chat testuale → stringa (per prompt compiler e simili)."""
    base = (api_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    messages: list[dict[str, str]] = []
    if system_message.strip():
        messages.append({"role": "system", "content": system_message.strip()})
    messages.append({"role": "user", "content": user_prompt.strip()})
    payload: dict[str, Any] = {
        "model": model.strip(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    tls = vision_httpx_tls_params(settings)
    with httpx.Client(
        timeout=timeout_s,
        verify=tls["verify"],
        trust_env=tls["trust_env"],
    ) as client:
        resp = client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI: risposta senza choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    text = str(content).strip()
    if not text:
        raise RuntimeError("OpenAI: risposta testuale vuota")
    return text
