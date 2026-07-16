"""Facebook Login (OAuth): browser → callback (localhost o tunnel) → user token → Page token file."""

from __future__ import annotations

import secrets
import ssl
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from social_automation.meta.token_tools import (
    exchange_authorization_code_for_short_lived_user_token,
)
from social_automation.settings import Settings

_DEFAULT_SCOPES = "pages_show_list"


def facebook_dialog_oauth_url(
    *,
    app_id: str,
    redirect_uri: str,
    state: str,
    graph_version: str,
    scopes: str = _DEFAULT_SCOPES,
    auth_type: str = "",
) -> str:
    """URL del dialog OAuth Facebook (response_type=code)."""
    v = graph_version.strip().lstrip("/") or "v22.0"
    params: dict[str, str] = {
        "client_id": app_id.strip(),
        "redirect_uri": redirect_uri.strip(),
        "state": state,
        "response_type": "code",
        "scope": scopes.strip(),
    }
    at = (auth_type or "").strip()
    if at:
        params["auth_type"] = at
    q = urlencode(params, quote_via=quote)
    return f"https://www.facebook.com/{v}/dialog/oauth?{q}"


class _OAuthState:
    __slots__ = ("code", "error", "error_description", "done")

    def __init__(self) -> None:
        self.code: str | None = None
        self.error: str | None = None
        self.error_description: str | None = None
        self.done = threading.Event()


class _OAuthHTTPServer(HTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        callback_path: str,
        expected_state: str,
        capture: _OAuthState,
    ) -> None:
        self.callback_path = callback_path
        self.expected_state = expected_state
        self.capture = capture
        super().__init__(server_address, handler)


class _OAuthHandler(BaseHTTPRequestHandler):
    server: _OAuthHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        s = self.server
        parsed = urlparse(self.path)
        if parsed.path != s.callback_path:
            self.send_response(404)
            self.end_headers()
            return
        q = parse_qs(parsed.query)
        if "error" in q:
            s.capture.error = (q.get("error") or [""])[0]
            s.capture.error_description = (q.get("error_description") or [""])[0]
            s.capture.done.set()
            self._html(400, "Errore OAuth. Puoi chiudere questa scheda.")
            return
        state = (q.get("state") or [""])[0]
        if state != s.expected_state:
            s.capture.error = "state_mismatch"
            s.capture.error_description = "Lo state OAuth non coincide."
            s.capture.done.set()
            self._html(400, "State non valido. Puoi chiudere questa scheda.")
            return
        code = (q.get("code") or [""])[0].strip()
        if not code:
            s.capture.error = "missing_code"
            s.capture.error_description = "Nessun code nella query."
            s.capture.done.set()
            self._html(400, "Code mancante. Puoi chiudere questa scheda.")
            return
        s.capture.code = code
        s.capture.done.set()
        self._html(200, "Login completato. Puoi chiudere questa scheda e tornare al terminale.")

    def _html(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<!DOCTYPE html><html><body><p>{body}</p></body></html>".encode("utf-8")
        )


def _normalize_callback_path(p: str) -> str:
    path = p or "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


def resolve_oauth_listen_target(
    redirect_uri: str,
    *,
    listen_port: int,
    ssl_certfile: str,
    ssl_keyfile: str,
) -> tuple[str, int, str, bool]:
    """
    Dove avviare il server locale e se usare TLS.

    Restituisce ``(bind_host, bind_port, callback_path, use_local_tls)``.

    - ``http(s)://127.0.0.1|localhost:PORT/path``: il server ascolta su quell'host/porta.
      Per ``https`` su loopback servono cert e key PEM (es. mkcert).
    - ``https://host-esterno/path`` (es. ngrok): Meta chiama HTTPS sul tunnel; il server
      locale ascolta in HTTP su ``127.0.0.1:listen_port`` (tunnel inoltra qui).
    """
    raw = redirect_uri.strip()
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    host = (p.hostname or "").lower()
    path = _normalize_callback_path(p.path)
    loop = host in {"127.0.0.1", "localhost"}

    if scheme not in {"http", "https"}:
        raise ValueError("META_REDIRECT_URI deve usare http o https.")

    if loop:
        bind_host = "127.0.0.1" if host == "localhost" else (p.hostname or "127.0.0.1")
        bind_port = p.port
        if bind_port is None:
            bind_port = 443 if scheme == "https" else 8765
        if scheme == "https":
            cert = (ssl_certfile or "").strip()
            key = (ssl_keyfile or "").strip()
            if not cert or not key:
                raise ValueError(
                    "HTTPS su localhost richiede META_OAUTH_TLS_CERTFILE e META_OAUTH_TLS_KEYFILE "
                    "(genera certificati con `mkcert 127.0.0.1` e punta ai file .pem). "
                    "In alternativa usa un tunnel ngrok: META_REDIRECT_URI=https://<tuo-subdominio>.ngrok-free.app/... "
                    "e `ngrok http META_OAUTH_LISTEN_PORT`."
                )
            cp = Path(cert)
            kp = Path(key)
            if not cp.is_file() or not kp.is_file():
                raise ValueError(f"Certificato OAuth TLS non trovato: cert={cp} key={kp}")
            return bind_host, int(bind_port), path, True
        return bind_host, int(bind_port), path, False

    if scheme != "https":
        raise ValueError(
            "Per redirect su host pubblico (es. ngrok) META_REDIRECT_URI deve usare https. "
            "Avvia `ngrok http <META_OAUTH_LISTEN_PORT>` e registra l'URL https completo nell'app Meta."
        )
    lp = max(1, min(65535, int(listen_port)))
    return "127.0.0.1", lp, path, False


def wait_for_facebook_oauth_code(
    *,
    redirect_uri: str,
    expected_state: str,
    timeout_s: float = 300.0,
    listen_port: int = 8765,
    ssl_certfile: str = "",
    ssl_keyfile: str = "",
) -> _OAuthState:
    bind_host, bind_port, path, use_tls = resolve_oauth_listen_target(
        redirect_uri,
        listen_port=listen_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
    capture = _OAuthState()
    httpd = _OAuthHTTPServer(
        (bind_host, bind_port),
        _OAuthHandler,
        callback_path=path,
        expected_state=expected_state,
        capture=capture,
    )
    if use_tls:
        cert = (ssl_certfile or "").strip()
        key = (ssl_keyfile or "").strip()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        if not capture.done.wait(timeout=timeout_s):
            raise TimeoutError(
                f"Timeout OAuth dopo {timeout_s:.0f}s: nessun callback ricevuto su {redirect_uri} "
                f"(server locale {bind_host}:{bind_port})."
            )
    finally:
        httpd.shutdown()
        thread.join(timeout=5.0)
    return capture


def open_browser_for_page_token_oauth(
    *,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    graph_version: str,
    scopes: str | None = None,
    auth_type: str = "",
    timeout_s: float = 300.0,
    open_browser: bool = True,
    listen_port: int = 8765,
    ssl_certfile: str = "",
    ssl_keyfile: str = "",
    settings: Settings | None = None,
) -> str:
    """
    Apre il browser per Facebook Login e restituisce lo **user access token** (breve).

    Richiede che ``redirect_uri`` sia registrato nell'app Meta (Facebook Login).
    """
    if not app_id.strip() or not app_secret.strip():
        raise ValueError("app_id e app_secret non possono essere vuoti")
    scope_str = (scopes or "").strip() or _DEFAULT_SCOPES
    state = secrets.token_urlsafe(24)
    url = facebook_dialog_oauth_url(
        app_id=app_id.strip(),
        redirect_uri=redirect_uri.strip(),
        state=state,
        graph_version=graph_version,
        scopes=scope_str,
        auth_type=auth_type,
    )
    if open_browser:
        webbrowser.open(url, new=1, autoraise=True)
    else:
        print("Apri questo URL nel browser (modalità --no-browser):\n")
        print(url)
    cap = wait_for_facebook_oauth_code(
        redirect_uri=redirect_uri,
        expected_state=state,
        timeout_s=timeout_s,
        listen_port=listen_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
    if cap.error:
        msg = cap.error_description or cap.error
        raise RuntimeError(f"OAuth Facebook fallito: {cap.error} — {msg}")
    if not cap.code:
        raise RuntimeError("OAuth Facebook: code assente dopo il callback.")
    return exchange_authorization_code_for_short_lived_user_token(
        app_id=app_id.strip(),
        app_secret=app_secret.strip(),
        redirect_uri=redirect_uri.strip(),
        code=cap.code,
        graph_version=graph_version,
        settings=settings,
    )
