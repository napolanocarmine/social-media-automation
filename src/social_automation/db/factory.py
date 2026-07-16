"""Selezione backend database (sqlite | postgres)."""

from __future__ import annotations

import os

from social_automation.settings import Settings, load_settings


def get_store_module(settings: Settings | None = None):
    s = settings or load_settings()
    backend = (s.db_backend or "sqlite").strip().lower()
    if os.environ.get("VERCEL") and backend != "postgres":
        raise RuntimeError(
            "Su Vercel serve DB_BACKEND=postgres e DATABASE_URL (integrazione Neon)."
        )
    if backend == "postgres":
        from social_automation.db import postgres_store

        url = (s.database_url or "").strip()
        if url:
            postgres_store.set_database_url(url)
        return postgres_store
    from social_automation.db import sqlite_store

    return sqlite_store


def get_database(settings: Settings | None = None):
    """Alias per compatibilità con doc Vercel."""
    return get_store_module(settings)
