"""Risoluzione variabili d'ambiente (integrazioni Vercel con prefisso)."""

from __future__ import annotations

import os


def resolve_database_url_from_env() -> str:
    """URL Postgres pooled per runtime.

    Vercel Neon può iniettare DATABASE_URL oppure variabili prefissate
    (es. NEON_DB_DATABASE_URL) se la risorsa ha un nome custom.
    """
    for key in ("DATABASE_URL", "TEST_DATABASE_URL"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val

    blocked = ("UNPOOLED", "NON_POOLING", "NO_SSL", "AUTH", "VITE")
    suffix_rank = {
        "_DATABASE_URL": 0,
        "_POSTGRES_URL": 1,
        "_POSTGRES_PRISMA_URL": 2,
    }

    best: tuple[int, str] | None = None
    for name, raw in os.environ.items():
        val = (raw or "").strip()
        if not val:
            continue
        upper = name.upper()
        if any(token in upper for token in blocked):
            continue
        for suffix, rank in suffix_rank.items():
            if upper.endswith(suffix):
                if best is None or rank < best[0]:
                    best = (rank, val)
                break

    return best[1] if best else ""


def resolve_blob_read_write_token_from_env() -> str:
    """Token Vercel Blob (anche variante prefissata, es. SOCIAL_MEDIA_AUTOMATION_BLOB_*)."""
    for key in ("BLOB_READ_WRITE_TOKEN", "VERCEL_BLOB_READ_WRITE_TOKEN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val

    best: tuple[int, str] | None = None
    for name, raw in os.environ.items():
        val = (raw or "").strip()
        if not val:
            continue
        upper = name.upper()
        if "READ_WRITE_TOKEN" not in upper:
            continue
        if "BLOB" not in upper:
            continue
        # Preferisci nomi corti / standard
        rank = 0 if upper == "BLOB_READ_WRITE_TOKEN" else 1
        if upper.endswith("_BLOB_READ_WRITE_TOKEN"):
            rank = 2
        if best is None or rank < best[0]:
            best = (rank, val)
    return best[1] if best else ""


def normalize_blob_store_id(store_id: str) -> str:
    raw = (store_id or "").strip()
    if raw.startswith("store_"):
        return raw[len("store_") :]
    return raw


def parse_blob_store_id_from_read_write_token(token: str) -> str:
    parts = (token or "").split("_")
    if len(parts) > 3 and parts[3]:
        return normalize_blob_store_id(parts[3])
    return ""


def resolve_blob_store_id_from_env() -> str:
    for key in ("BLOB_STORE_ID", "VERCEL_BLOB_STORE_ID"):
        val = normalize_blob_store_id(os.environ.get(key) or "")
        if val:
            return val

    best: tuple[int, str] | None = None
    for name, raw in os.environ.items():
        val = normalize_blob_store_id(raw or "")
        if not val:
            continue
        upper = name.upper()
        if not upper.endswith("_BLOB_STORE_ID") and upper != "BLOB_STORE_ID":
            continue
        rank = 0 if upper == "BLOB_STORE_ID" else 1
        if best is None or rank < best[0]:
            best = (rank, val)
    return best[1] if best else ""


def resolve_vercel_oidc_token_from_env() -> str:
    return (os.environ.get("VERCEL_OIDC_TOKEN") or "").strip()


def blob_storage_configured_from_env() -> bool:
    """True se OIDC+store o read-write token sono disponibili."""
    if resolve_blob_read_write_token_from_env():
        return True
    return bool(
        resolve_vercel_oidc_token_from_env() and resolve_blob_store_id_from_env()
    )
