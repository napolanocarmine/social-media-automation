"""Opzioni httpx comuni per le chiamate TLS a graph.facebook.com."""

from __future__ import annotations

from typing import Any

from social_automation.http.httpx_tls import httpx_tls_params
from social_automation.settings import Settings, load_settings


def graph_httpx_tls_params(settings: Settings | None = None) -> dict[str, Any]:
    """
    Restituisce ``verify`` e ``trust_env`` per ``httpx.Client`` verso Graph.

    Con ``META_GRAPH_HTTP_TRUST_ENV=false`` httpx non applica proxy da variabili
    d'ambiente (``HTTP_PROXY`` / ``HTTPS_PROXY``), utile se un proxy MITM inserisce
    una catena con CA non presente nel bundle predefinito e compare
    ``CERTIFICATE_VERIFY_FAILED``.
    """
    s = settings if settings is not None else load_settings()
    return httpx_tls_params(
        trust_env=bool(s.meta_graph_http_trust_env),
        ca_bundle=(s.meta_graph_http_ca_bundle or "").strip(),
    )
