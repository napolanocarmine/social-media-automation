#!/usr/bin/env python3
"""Genera .env.vercel.import per import bulk su Vercel (Settings → Environment Variables → Import).

Uso:
  python3 scripts/generate_vercel_env.py
  python3 scripts/generate_vercel_env.py --app-url https://social-media-automation-typin.vercel.app

Legge (se presenti):
  credentials.json  → GOOGLE_CREDENTIALS_JSON
  token.json        → GOOGLE_REFRESH_TOKEN

Non committare il file generato (contiene segreti).
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".env.vercel.import"


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Errore JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _minify_json(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _refresh_from_token(token_path: Path) -> str:
    data = _read_json(token_path)
    if not data:
        return ""
    return str(data.get("refresh_token") or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera .env.vercel.import per Vercel")
    parser.add_argument(
        "--app-url",
        default="https://social-media-automation-typin.vercel.app",
        help="URL produzione (senza slash finale)",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=ROOT / "credentials.json",
        help="Path OAuth client JSON Google",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=ROOT / "token.json",
        help="Path token.json dopo drive-auth locale",
    )
    parser.add_argument(
        "--cron-secret",
        default="",
        help="CRON_SECRET (vuoto = genera random)",
    )
    args = parser.parse_args()

    app_url = args.app_url.rstrip("/")
    creds_path = args.credentials.expanduser()
    token_path = args.token.expanduser()

    creds_obj = _read_json(creds_path)
    creds_line = _minify_json(creds_obj) if creds_obj else ""
    refresh = _refresh_from_token(token_path)
    cron = (args.cron_secret or "").strip() or secrets.token_urlsafe(32)

    oauth_type = ""
    if creds_obj:
        if "web" in creds_obj:
            oauth_type = "web"
        elif "installed" in creds_obj:
            oauth_type = "installed (Desktop)"

    lines = [
        "# Generato da scripts/generate_vercel_env.py — NON committare",
        "# Vercel → Project → Settings → Environment Variables → Import .env",
        "# Ambiente: seleziona Production (+ Preview se serve)",
        "#",
        "# Neon e Blob: se già collegati da integrazione, NON duplicare manualmente.",
        "# Blob: OIDC (VERCEL_OIDC_TOKEN + BLOB_STORE_ID) o BLOB_READ_WRITE_TOKEN prefissato.",
        "",
        "# === App (obbligatori) ===",
        f"API_CORS_ORIGINS={app_url}",
        "APP_TIMEZONE=Europe/Rome",
        "DB_BACKEND=postgres",
        "STORAGE_BACKEND=vercel_blob",
        "",
        "# === Google Drive (obbligatori per Seleziona / anteprime) ===",
    ]

    if creds_line:
        lines.append(f"GOOGLE_CREDENTIALS_JSON={creds_line}")
    else:
        lines.append("# GOOGLE_CREDENTIALS_JSON=<incolla JSON OAuth client su una riga>")

    if refresh:
        lines.append(f"GOOGLE_REFRESH_TOKEN={refresh}")
    else:
        lines.extend(
            [
                "# GOOGLE_REFRESH_TOKEN=<dopo drive-auth locale o /api/v1/oauth/google/start>",
                "# Per refresh token locale:",
                "#   python3 -m social_automation drive-auth",
                "#   poi rilancia questo script",
            ]
        )

    lines.extend(
        [
            f"GOOGLE_REDIRECT_URI={app_url}/api/v1/oauth/google/callback",
            "",
            "# === Cron dispatch ===",
            f"CRON_SECRET={cron}",
            "DISPATCH_REQUIRE_APPROVAL=true",
            "DISPATCH_REQUIRE_QUALITY_PASS=false",
            "DISPATCH_LIMIT=100",
            "DISPATCH_CRON_HOUR_START=11",
            "DISPATCH_CRON_HOUR_END=22",
            "",
            "# === Meta (quando abiliti pubblicazione) ===",
            "META_APP_ID=",
            "META_APP_SECRET=",
            "META_PAGE_ACCESS_TOKEN=",
            "META_IG_USER_ID=",
            "META_GRAPH_VERSION=v22.0",
            "",
            "# === Story AI (quando abiliti batch AI) ===",
            "VISION_API_KEY=",
            "VISION_MODEL=gpt-4o-mini",
            "",
        ]
    )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Scritto: {OUT}")
    if oauth_type == "installed (Desktop)":
        print()
        print("Nota: credentials.json è tipo Desktop.")
        print("  • Su Vercel funziona se imposti GOOGLE_REFRESH_TOKEN (es. da drive-auth locale).")
        print("  • Per OAuth diretto su Vercel (/api/v1/oauth/google/start) crea anche un client Web")
        print(f"    con redirect: {app_url}/api/v1/oauth/google/callback")
    if not refresh:
        print()
        print("Manca GOOGLE_REFRESH_TOKEN. Esegui in locale:")
        print("  python3 -m social_automation drive-auth")
        print("  python3 scripts/generate_vercel_env.py")


if __name__ == "__main__":
    main()
