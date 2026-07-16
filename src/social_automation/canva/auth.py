"""OAuth helper per Canva Connect APIs (Authorization Code + PKCE)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


def normalize_scopes(raw: str) -> list[str]:
    """Accetta scope separati da spazio o virgola."""
    return [s for s in raw.replace(",", " ").split() if s]


def generate_code_verifier() -> str:
    # 64 bytes random -> base64url ~86 chars (valido PKCE: 43-128)
    return secrets.token_urlsafe(64)


def generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str,
    state: str,
) -> str:
    params = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": " ".join(scopes),
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri,
    }
    return f"{CANVA_AUTH_URL}?{urlencode(params)}"


def extract_code_from_input(user_input: str) -> str:
    """Accetta un codice puro o l'intero URL di callback."""
    cleaned = user_input.strip()
    if "://" in cleaned:
        parsed = urlparse(cleaned)
        code = parse_qs(parsed.query).get("code", [""])[0]
        if not code:
            raise ValueError("URL callback senza parametro 'code'.")
        return code
    return cleaned


class _OAuthCallbackServer(HTTPServer):
    auth_code: str | None = None
    state: str | None = None


def _build_handler(expected_path: str):
    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            query = parse_qs(parsed.query)
            code = query.get("code", [""])[0]
            state = query.get("state", [""])[0]
            self.server.auth_code = code
            self.server.state = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h3>Autorizzazione completata.</h3>"
                b"<p>Puoi chiudere questa scheda e tornare al terminale.</p>"
                b"</body></html>"
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            _ = (format, args)
            return

    return OAuthCallbackHandler


def wait_for_callback_code(redirect_uri: str, *, timeout_seconds: int = 180) -> tuple[str, str]:
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or ""
    port = parsed.port
    path = parsed.path or "/"
    if parsed.scheme != "http":
        raise ValueError("Redirect URI deve usare schema http in locale.")
    if host not in {"127.0.0.1", "localhost"} or not port:
        raise ValueError("Redirect URI deve essere locale, es. http://127.0.0.1:8080/callback")

    server = _OAuthCallbackServer((host, port), _build_handler(path))
    server.timeout = 1
    deadline = time.time() + timeout_seconds
    try:
        while time.time() < deadline:
            server.handle_request()
            if server.auth_code:
                return server.auth_code, server.state or ""
    finally:
        server.server_close()
    raise TimeoutError("Timeout callback OAuth Canva: nessun codice ricevuto.")


def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            CANVA_TOKEN_URL,
            data=payload,
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Errore token Canva ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


def save_token(token: dict[str, Any], token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")


def run_canva_oauth(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: list[str],
    token_path: Path,
    open_browser: bool = True,
) -> Path:
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    expected_state = generate_state()
    auth_url = build_authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        code_challenge=code_challenge,
        state=expected_state,
    )
    print("Apri e autorizza Canva su questo URL:")
    print(auth_url)
    if open_browser:
        webbrowser.open(auth_url)
        code, received_state = wait_for_callback_code(redirect_uri)
    else:
        callback_input = input("Incolla qui URL callback completo (o solo code): ").strip()
        code = extract_code_from_input(callback_input)
        parsed = urlparse(callback_input) if "://" in callback_input else None
        received_state = parse_qs(parsed.query).get("state", [""])[0] if parsed else expected_state

    if received_state and received_state != expected_state:
        raise RuntimeError("State OAuth non valido. Riprova l'autenticazione.")

    token = exchange_authorization_code(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )
    save_token(token, token_path)
    return token_path
