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
