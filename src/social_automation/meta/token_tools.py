"""Utility per rinnovare Page access token via Graph (fb_exchange_token + me/accounts)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from social_automation.meta.graph_httpx import graph_httpx_tls_params
from social_automation.settings import Settings

_DEFAULT_VERSION = "v22.0"

_GRAPH_TLS_USER_HINT = (
    "TLS verso graph.facebook.com fallita (verifica certificato). "
    "Spesso è un proxy/VPN (es. HTTPS_PROXY) che intercetta HTTPS (self-signed in chain). "
    "Prova: meta-oauth-page-token --graph-no-proxy "
    "o meta-refresh-page-token --graph-no-proxy "
    "oppure nel .env META_GRAPH_HTTP_TRUST_ENV=false "
    "(httpx non usa più proxy da variabili d'ambiente verso Meta). "
    "In ambiente aziendale con SSL inspection serve META_GRAPH_HTTP_CA_BUNDLE "
    "(PEM della CA del proxy)."
)


def graph_root(version: str) -> str:
    v = (version or _DEFAULT_VERSION).strip().lstrip("/") or _DEFAULT_VERSION
    return f"https://graph.facebook.com/{v}"


def _raise_for_graph(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        data = resp.json()
        err = data.get("error") or {}
        msg = err.get("message", resp.text[:500])
        code = err.get("code", "")
        sub = err.get("error_subcode", "")
        raise RuntimeError(f"Meta Graph API ({resp.status_code}) [{code}/{sub}]: {msg}")
    except (ValueError, TypeError):
        raise RuntimeError(f"Meta Graph API ({resp.status_code}): {resp.text[:800]}") from None


def exchange_user_token_for_long_lived(
    *,
    app_id: str,
    app_secret: str,
    user_access_token: str,
    graph_version: str = _DEFAULT_VERSION,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Scambia un user access token (tipicamente breve) in long-lived (~60 giorni).

    Documentazione Meta: GET /oauth/access_token con grant_type=fb_exchange_token.
    """
    aid = app_id.strip()
    sec = app_secret.strip()
    uat = user_access_token.strip()
    if not aid or not sec or not uat:
        raise ValueError("app_id, app_secret e user_access_token non possono essere vuoti")
    base = graph_root(graph_version)
    tls = graph_httpx_tls_params(settings)
    try:
        with httpx.Client(timeout=60.0, verify=tls["verify"], trust_env=tls["trust_env"]) as client:
            r = client.get(
                f"{base}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": aid,
                    "client_secret": sec,
                    "fb_exchange_token": uat,
                },
            )
    except httpx.ConnectError as e:
        err = str(e).lower()
        if "certificate" in err or "ssl" in err:
            raise RuntimeError(_GRAPH_TLS_USER_HINT) from e
        raise
    _raise_for_graph(r)
    return r.json()


def fetch_user_page_accounts(
    *,
    user_access_token: str,
    graph_version: str = _DEFAULT_VERSION,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Elenco Page gestite dall'utente con relativi Page access token."""
    uat = user_access_token.strip()
    if not uat:
        raise ValueError("user_access_token non può essere vuoto")
    base = graph_root(graph_version)
    tls = graph_httpx_tls_params(settings)
    try:
        with httpx.Client(timeout=60.0, verify=tls["verify"], trust_env=tls["trust_env"]) as client:
            r = client.get(
                f"{base}/me/accounts",
                params={
                    "fields": "id,name,access_token,tasks",
                    "access_token": uat,
                },
            )
    except httpx.ConnectError as e:
        err = str(e).lower()
        if "certificate" in err or "ssl" in err:
            raise RuntimeError(_GRAPH_TLS_USER_HINT) from e
        raise
    _raise_for_graph(r)
    data = r.json().get("data") or []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def pick_page_token(
    pages: list[dict[str, Any]],
    *,
    page_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Sceglie la Page e restituisce (page_access_token, voce page)."""
    pid = (page_id or "").strip()
    if not pages:
        raise RuntimeError("Nessuna Facebook Page in me/accounts per questo utente/token.")
    if pid:
        for row in pages:
            if str(row.get("id", "")).strip() == pid:
                tok = str(row.get("access_token", "")).strip()
                if not tok:
                    raise RuntimeError(f"Page {pid}: access_token mancante nella risposta.")
                return tok, row
        names = ", ".join(f"{r.get('id')}:{r.get('name')}" for r in pages[:20])
        raise RuntimeError(
            f"Page id {pid} non trovata tra le Page dell'utente. Disponibili: {names}"
        )
    if len(pages) == 1:
        row = pages[0]
        tok = str(row.get("access_token", "")).strip()
        if not tok:
            raise RuntimeError("Unica Page in elenco ma access_token mancante.")
        return tok, row
    lines = "\n".join(f"  {r.get('id')}\t{r.get('name')}" for r in pages)
    raise RuntimeError(
        "Sono presenti più Page: passa --page-id con l'id numerico della Page.\n" + lines
    )


def persist_page_token_from_user_token(
    *,
    user_access_token: str,
    app_id: str,
    app_secret: str,
    graph_version: str,
    page_id: str | None,
    skip_exchange: bool,
    output_path: Path,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    User token → (opz.) long-lived → me/accounts → Page token salvato su ``output_path``.

    Restituisce (exchange_json_o_summary, page_row) dove exchange_json è {} se skip_exchange.
    """
    aid = app_id.strip()
    sec = app_secret.strip()
    uat = user_access_token.strip()
    if not aid or not sec or not uat:
        raise ValueError("app_id, app_secret e user_access_token non possono essere vuoti")
    exchange_info: dict[str, Any] = {}
    if skip_exchange:
        long_lived = uat
    else:
        exchange_info = exchange_user_token_for_long_lived(
            app_id=aid,
            app_secret=sec,
            user_access_token=uat,
            graph_version=graph_version,
            settings=settings,
        )
        long_lived = str(exchange_info.get("access_token", "")).strip()
        if not long_lived:
            raise RuntimeError(f"Scambio token: risposta inattesa: {exchange_info}")
    pages = fetch_user_page_accounts(
        user_access_token=long_lived, graph_version=graph_version, settings=settings
    )
    page_token, row = pick_page_token(pages, page_id=page_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page_token + "\n", encoding="utf-8")
    try:
        output_path.chmod(0o600)
    except OSError:
        pass
    return exchange_info, row


def exchange_authorization_code_for_short_lived_user_token(
    *,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
    graph_version: str = _DEFAULT_VERSION,
    settings: Settings | None = None,
) -> str:
    """Scambia il ``code`` del redirect OAuth in user access token (tipicamente breve)."""
    aid = app_id.strip()
    sec = app_secret.strip()
    uri = redirect_uri.strip()
    c = code.strip()
    if not aid or not sec or not uri or not c:
        raise ValueError("app_id, app_secret, redirect_uri e code non possono essere vuoti")
    base = graph_root(graph_version)
    tls = graph_httpx_tls_params(settings)
    try:
        with httpx.Client(timeout=60.0, verify=tls["verify"], trust_env=tls["trust_env"]) as client:
            r = client.get(
                f"{base}/oauth/access_token",
                params={
                    "client_id": aid,
                    "redirect_uri": uri,
                    "client_secret": sec,
                    "code": c,
                },
            )
    except httpx.ConnectError as e:
        err = str(e).lower()
        if "certificate" in err or "ssl" in err:
            raise RuntimeError(_GRAPH_TLS_USER_HINT) from e
        raise
    _raise_for_graph(r)
    data = r.json()
    tok = str(data.get("access_token", "")).strip()
    if not tok:
        raise RuntimeError(f"code exchange: risposta inattesa: {data}")
    return tok


def debug_input_token(
    *,
    input_token: str,
    app_id: str,
    app_secret: str,
    graph_version: str = _DEFAULT_VERSION,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Decodifica un access token con ``GET /debug_token`` (``access_token`` = ``app_id|app_secret``).

    Nella risposta, ``data.scopes`` / ``data.granular_scopes`` mostrano i permessi associati al token.
    """
    aid = app_id.strip()
    sec = app_secret.strip()
    it = input_token.strip()
    if not aid or not sec or not it:
        raise ValueError("app_id, app_secret e input_token non possono essere vuoti")
    base = graph_root(graph_version)
    app_access = f"{aid}|{sec}"
    tls = graph_httpx_tls_params(settings)
    try:
        with httpx.Client(timeout=60.0, verify=tls["verify"], trust_env=tls["trust_env"]) as client:
            r = client.get(
                f"{base}/debug_token",
                params={"input_token": it, "access_token": app_access},
            )
    except httpx.ConnectError as e:
        err = str(e).lower()
        if "certificate" in err or "ssl" in err:
            raise RuntimeError(_GRAPH_TLS_USER_HINT) from e
        raise
    _raise_for_graph(r)
    return r.json()
