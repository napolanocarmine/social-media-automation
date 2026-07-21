"""Helper condivisi per test store sqlite/postgres."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


def is_postgres_backend() -> bool:
    return (os.environ.get("DB_BACKEND") or "sqlite").strip().lower() == "postgres"


def execute_sql(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    if is_postgres_backend():
        from social_automation.db import postgres_store

        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            postgres_store.set_database_url(url)
        pg_sql = sql.replace("?", "%s")
        with postgres_store._connect(db_path) as conn:
            conn.execute(pg_sql, params)
        return
    with sqlite3.connect(db_path) as conn:
        conn.execute(sql, params)
        conn.commit()


def fetchone_sql(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
    if is_postgres_backend():
        from social_automation.db import postgres_store

        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            postgres_store.set_database_url(url)
        pg_sql = sql.replace("?", "%s")
        with postgres_store._connect(db_path) as conn:
            row = conn.execute(pg_sql, params).fetchone()
        if row is None:
            return None
        return _normalize_row(tuple(row.values()))

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return _normalize_row(row)


def fetchall_sql(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if is_postgres_backend():
        from social_automation.db import postgres_store

        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            postgres_store.set_database_url(url)
        pg_sql = sql.replace("?", "%s")
        with postgres_store._connect(db_path) as conn:
            rows = conn.execute(pg_sql, params).fetchall()
        return [_normalize_row(tuple(r.values())) for r in rows]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_normalize_row(r) for r in rows]


def table_columns(db_path: Path, table: str) -> list[str]:
    if is_postgres_backend():
        from social_automation.db import postgres_store

        url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        if url:
            postgres_store.set_database_url(url)
        with postgres_store._connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            ).fetchall()
        return [str(r["column_name"]) for r in rows]

    with sqlite3.connect(db_path) as conn:
        return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def metadata_json_payload(md: dict[str, Any]) -> dict[str, Any]:
    raw = md.get("metadata_json")
    if isinstance(raw, dict):
        return raw
    return json.loads(str(raw))


def _normalize_row(row: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(_normalize_value(v) for v in row)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        text = value.isoformat()
        if text.endswith("+00:00"):
            return text[:-6]
        return text
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


requires_sqlite = pytest.mark.skipif(is_postgres_backend(), reason="sqlite-only migration test")
