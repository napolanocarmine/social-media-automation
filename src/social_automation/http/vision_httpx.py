"""Opzioni httpx per API OpenAI-compatible (Vision, Story AI, image edit)."""

from __future__ import annotations

from typing import Any

from social_automation.http.httpx_tls import httpx_tls_params
from social_automation.settings import Settings, load_settings


def vision_httpx_tls_params(settings: Settings | None = None) -> dict[str, Any]:
    """
    TLS/proxy per chiamate a ``api.openai.com`` (o ``VISION_API_BASE_URL``).

    Se ``VISION_HTTP_TRUST_ENV`` / ``VISION_HTTP_CA_BUNDLE`` non sono impostati,
    eredita ``META_GRAPH_HTTP_TRUST_ENV`` e ``META_GRAPH_HTTP_CA_BUNDLE``.
    """
    s = settings if settings is not None else load_settings()
    trust_env = (
        s.meta_graph_http_trust_env
        if s.vision_http_trust_env is None
        else bool(s.vision_http_trust_env)
    )
    bundle = (s.vision_http_ca_bundle or s.meta_graph_http_ca_bundle or "").strip()
    return httpx_tls_params(trust_env=trust_env, ca_bundle=bundle)
