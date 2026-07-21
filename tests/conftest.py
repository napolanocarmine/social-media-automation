"""Fixture pytest condivise."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from social_automation.db import reset_backend


@pytest.fixture(autouse=True)
def _reset_db_backend():
    reset_backend()
    yield
    reset_backend()


@pytest.fixture
def db_path(tmp_path: Path, db_backend_module):
    path = tmp_path / "db.sqlite3"
    backend = (os.environ.get("DB_BACKEND") or "sqlite").strip().lower()
    if backend == "postgres":
        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            db_backend_module.set_database_url(url)
        db_backend_module.ensure_db_schema(path)
        if hasattr(db_backend_module, "truncate_all_tables_for_tests"):
            db_backend_module.truncate_all_tables_for_tests(path)
    return path


@pytest.fixture
def db_backend_module():
    backend = (os.environ.get("DB_BACKEND") or "sqlite").strip().lower()
    if backend == "postgres":
        from social_automation.db import postgres_store

        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            postgres_store.set_database_url(url)
        return postgres_store
    from social_automation.db import sqlite_store

    return sqlite_store
