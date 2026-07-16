"""Opzioni TLS comuni per client httpx."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def httpx_tls_params(*, trust_env: bool, ca_bundle: str) -> dict[str, Any]:
    """
    Restituisce ``verify`` e ``trust_env`` per ``httpx.Client``.

    Con ``trust_env=false`` httpx non applica proxy da variabili d'ambiente
    (``HTTP_PROXY`` / ``HTTPS_PROXY``), utile se un proxy MITM inserisce una
    catena con CA non presente nel bundle predefinito.
    """
    bundle = (ca_bundle or "").strip()
    verify: str | bool = True
    if bundle:
        p = Path(bundle)
        if p.is_file():
            verify = str(p.resolve())
    return {"verify": verify, "trust_env": bool(trust_env)}
