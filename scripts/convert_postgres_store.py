#!/usr/bin/env python3
"""Converte sqlite_store.py in postgres_store.py."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/social_automation/db/sqlite_store.py"
DST = ROOT / "src/social_automation/db/postgres_store.py"

HEADER = '''"""Persistenza Neon Postgres per stato render, metadati e pianificazione."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from social_automation.models import MediaFormat, Platform
from social_automation.app_timezone import query_datetime_utc, scheduled_for_db_iso

_LOG = logging.getLogger(__name__)
_database_url: str | None = None


def set_database_url(url: str) -> None:
    global _database_url
    _database_url = url.strip()


def _get_database_url() -> str:
    global _database_url
    if _database_url is None:
        url = (os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL o TEST_DATABASE_URL non configurato")
        _database_url = url
    return _database_url


@contextmanager
def _connect(db_path: Path | None = None) -> Iterator[psycopg.Connection]:
    del db_path
    with psycopg.connect(_get_database_url(), row_factory=dict_row) as conn:
        yield conn
        conn.commit()


def _table_columns(conn: psycopg.Connection, table_name: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {str(r["column_name"]) for r in rows}


def ensure_db_schema(db_path: Path) -> None:
    del db_path
    with _connect() as conn:
        conn.execute("SELECT 1")


'''

TAIL = '''

def get_next_queued_batch_item(db_path: Path) -> dict[str, Any] | None:
    """Prossimo batch_item in coda (status=queued), FIFO."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT bi.*, b.stop_requested_at
            FROM batch_items bi
            JOIN batches b ON b.id = bi.batch_id
            WHERE bi.status = 'queued'
              AND b.status = 'running'
              AND b.stop_requested_at IS NULL
            ORDER BY bi.created_at ASC, bi.id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        ).fetchone()
    return dict(row) if row else None
'''


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    start = text.index("def _upsert_image")
    body = text[start:]

    body = body.replace("sqlite3.Connection", "psycopg.Connection")
    body = body.replace("datetime('now')", "NOW()")
    body = body.replace("?", "%s")
    body = body.replace(
        "julianday(r.scheduled_for) <= julianday(%s)",
        "r.scheduled_for <= %s::timestamptz",
    )
    body = body.replace(
        "julianday(r.scheduled_for) >= julianday(%s)",
        "r.scheduled_for >= %s::timestamptz",
    )
    body = body.replace(
        "julianday(r.scheduled_for) < julianday(%s)",
        "r.scheduled_for < %s::timestamptz",
    )
    body = body.replace("INSERT OR REPLACE INTO", "INSERT INTO")
    body = body.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    body = body.replace("runner_pid, ", "")
    body = body.replace("runner_pid,\n              ", "")

    batch_upsert_old = (
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n"
        '            """'
    )
    batch_upsert_new = (
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n"
        "            ON CONFLICT (batch_id, item_index) DO UPDATE SET\n"
        "              status = EXCLUDED.status,\n"
        "              source_asset_id = EXCLUDED.source_asset_id,\n"
        "              source_asset_name = EXCLUDED.source_asset_name,\n"
        "              business_category = EXCLUDED.business_category,\n"
        "              template_id = EXCLUDED.template_id,\n"
        "              image_id = EXCLUDED.image_id,\n"
        "              rendered_file = EXCLUDED.rendered_file,\n"
        "              error_message = EXCLUDED.error_message,\n"
        "              payload_json = EXCLUDED.payload_json,\n"
        "              media_format = EXCLUDED.media_format\n"
        '            """'
    )
    body = body.replace(batch_upsert_old, batch_upsert_new)

    body = body.replace(
        "INSERT INTO story_schedule_occurrences(rule_id, occurrence_date) VALUES (%s, %s)",
        "INSERT INTO story_schedule_occurrences(rule_id, occurrence_date) VALUES (%s, %s) ON CONFLICT (rule_id, occurrence_date) DO NOTHING",
    )

    body = body.replace(
        '"INSERT INTO images(name, path) VALUES(%s, %s)"',
        '"INSERT INTO images(name, path) VALUES(%s, %s) RETURNING id"',
    )
    body = body.replace(
        """            VALUES (%s, %s, %s, %s, %s, %s)
            """,
        """            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
        1,
    )

    mark_batch_repl = (
        "def mark_batch_runner_pid(db_path: Path, *, batch_id: int, runner_pid: int | None) -> None:\n"
        "    del db_path, batch_id, runner_pid\n\n\n"
        "def request_batch_stop"
    )

    body = re.sub(
        r"def mark_batch_runner_pid\([\s\S]*?def request_batch_stop",
        mark_batch_repl,
        body,
        count=1,
    )

    body = body.replace(
        "    cur = conn.execute(\n        \"INSERT INTO images(name, path) VALUES(%s, %s) RETURNING id\",\n        (name, path),\n    )\n    return int(cur.lastrowid)",
        "    row = conn.execute(\n        \"INSERT INTO images(name, path) VALUES(%s, %s) RETURNING id\",\n        (name, path),\n    ).fetchone()\n    return int(row[\"id\"])",
    )

    body = body.replace(
        "        cur = conn.execute(\"DELETE FROM images WHERE is_valid_for_publication IS NULL\")\n        return int(cur.rowcount)",
        "        cur = conn.execute(\"DELETE FROM images WHERE is_valid_for_publication IS NULL\")\n        return int(cur.rowcount)",
    )

    body = body.replace(
        "        )\n        return int(cur.lastrowid)",
        "        ).fetchone()\n        return int(row[\"id\"])",
        1,
    )
    body = body.replace(
        "        cur = conn.execute(\n            \"\"\"\n            INSERT INTO batches(",
        "        row = conn.execute(\n            \"\"\"\n            INSERT INTO batches(",
        1,
    )

    body = body.replace("return cur.rowcount == 1", "return cur.rowcount == 1")

    DST.write_text(HEADER + body + TAIL, encoding="utf-8")
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
