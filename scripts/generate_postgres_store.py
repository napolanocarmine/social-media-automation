#!/usr/bin/env python3
"""Genera postgres_store.py da sqlite_store.py con adattamenti SQL."""

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


def _get_database_url() -> str:
    global _database_url
    if _database_url is None:
        url = (os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL o TEST_DATABASE_URL non configurato")
        _database_url = url
    return _database_url


def set_database_url(url: str) -> None:
    """Imposta URL DB (utile nei test)."""
    global _database_url
    _database_url = url.strip()


@contextmanager
def _connect(db_path: Path | None = None) -> Iterator[psycopg.Connection]:
    del db_path  # compatibilità firma sqlite
    with psycopg.connect(_get_database_url(), row_factory=dict_row) as conn:
        yield conn
        conn.commit()


def _table_columns(conn: psycopg.Connection, table_name: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    ).fetchall()
    return {str(r["column_name"]) for r in rows}


def ensure_db_schema(db_path: Path) -> None:
    """Schema applicato via docs/sql/001_initial_schema.sql — verifica connessione."""
    del db_path
    with _connect() as conn:
        conn.execute("SELECT 1")


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


'''

SKIP_PREFIXES = (
    '"""Persistenza',
    "import sqlite3",
    "from social_automation.models",
    "from social_automation.app_timezone",
    "_LOG = logging.getLogger",
)


def should_skip_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for prefix in SKIP_PREFIXES:
        if stripped.startswith(prefix) or line.startswith(prefix):
            return True
    if stripped.startswith("def _normalize_media_format"):
        return True
    if stripped.startswith("def _connect"):
        return True
    if stripped.startswith("def _table_columns"):
        return True
    if stripped.startswith("def _create_"):
        return True
    if stripped.startswith("def _migrate_"):
        return True
    if stripped.startswith("def ensure_db_schema"):
        return True
    return False


def transform_body(text: str) -> str:
    text = text.replace("sqlite3.Connection", "psycopg.Connection")
    text = text.replace("datetime('now')", "NOW()")
    text = re.sub(
        r"julianday\(r\.scheduled_for\)\s*<=\s*julianday\(\?\)",
        "r.scheduled_for <= %s::timestamptz",
        text,
    )
    text = re.sub(
        r"julianday\(r\.scheduled_for\)\s*>=\s*julianday\(\?\)",
        "r.scheduled_for >= %s::timestamptz",
        text,
    )
    text = re.sub(
        r"julianday\(r\.scheduled_for\)\s*<\s*julianday\(\?\)",
        "r.scheduled_for < %s::timestamptz",
        text,
    )
    text = text.replace("INSERT OR REPLACE INTO", "INSERT INTO")
    text = text.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    text = text.replace("?", "%s")

    # lastrowid → RETURNING id
    text = re.sub(
        r"cur = conn\.execute\(\s*\"\"\"\s*INSERT INTO batches\(([^)]+)\)\s*VALUES \(([^)]+)\)\s*\"\"\",\s*([^)]+)\),\s*\)\s*return int\(cur\.lastrowid\)",
        r'row = conn.execute("""INSERT INTO batches(\1) VALUES (\2) RETURNING id""", \3).fetchone()\n        return int(row["id"])',
        text,
        flags=re.DOTALL,
    )

    # Generic lastrowid for images insert patterns - handle manually in extras

    # ON CONFLICT for batch_items upsert
    if "INSERT INTO batch_items(" in text and "ON CONFLICT" not in text:
        text = text.replace(
            """            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            """            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (batch_id, item_index) DO UPDATE SET
              status = EXCLUDED.status,
              source_asset_id = EXCLUDED.source_asset_id,
              source_asset_name = EXCLUDED.source_asset_name,
              business_category = EXCLUDED.business_category,
              template_id = EXCLUDED.template_id,
              image_id = EXCLUDED.image_id,
              rendered_file = EXCLUDED.rendered_file,
              error_message = EXCLUDED.error_message,
              payload_json = EXCLUDED.payload_json,
              media_format = EXCLUDED.media_format
            """,
        )

    # story occurrences ON CONFLICT
    text = text.replace(
        "INSERT INTO story_schedule_occurrences(rule_id, occurrence_date) VALUES (%s, %s)",
        "INSERT INTO story_schedule_occurrences(rule_id, occurrence_date) VALUES (%s, %s) ON CONFLICT (rule_id, occurrence_date) DO NOTHING",
    )

    # JSON columns: use json.dumps for JSONB in inserts where needed - keep json.dumps

    # Remove runner_pid from SELECT/UPDATE where postgres schema lacks it
    text = text.replace("runner_pid,\n              ", "")
    text = text.replace("runner_pid, ", "")
    text = text.replace("SET runner_pid = %s, updated_at", "SET updated_at")

    return text


def extract_functions(src: str) -> str:
    lines = src.splitlines()
    out: list[str] = []
    skipping = False
    skip_depth = 0
    for line in lines:
        if line.startswith("def _normalize_media_format"):
            skipping = True
            skip_depth = 0
        if skipping:
            if line.startswith("def ") and not line.startswith("def _normalize"):
                skipping = False
            else:
                continue
        if should_skip_line(line):
            continue
        out.append(line)
    return "\n".join(out)


EXTRA_FUNCTIONS = '''

def get_next_queued_batch_item(db_path: Path) -> dict[str, Any] | None:
    """Prossimo batch_item in coda (status=queued), FIFO."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT bi.*, b.stop_requested_at, b.status AS batch_status
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


def mark_batch_runner_pid(
    db_path: Path,
    *,
    batch_id: int,
    runner_pid: int | None,
) -> None:
    """No-op su Postgres — queue-based, nessun PID."""
    del db_path, batch_id, runner_pid


'''


def main() -> None:
    src_text = SRC.read_text(encoding="utf-8")
    # extract _normalize_media_format from sqlite
    norm_match = re.search(
        r"(def _normalize_media_format[\s\S]*?return MediaFormat\.POST\.value\n)",
        src_text,
    )
    norm_fn = norm_match.group(1) if norm_match else ""

    body_start = src_text.index("def _upsert_image")
    body = src_text[body_start:]
    body = extract_functions(body)
    body = transform_body(body)

    # Fix create_batch RETURNING
    body = body.replace(
        """            )
        )
        return int(cur.lastrowid)""",
        """            )
            RETURNING id
            """
        ).fetchone()
        return int(row["id"])""",
        1,
    )

    # Fix _upsert_image and other lastrowid patterns
    body = re.sub(
        r"return int\(cur\.lastrowid\)",
        'row = conn.execute("SELECT currval(pg_get_serial_sequence(\'images\', \'id\')) AS id").fetchone()\n        return int(row["id"])',
        body,
    )

    # mark_batch_runner_pid noop in body - replace function
    body = re.sub(
        r"def mark_batch_runner_pid\([\s\S]*?def request_batch_stop",
        "def request_batch_stop",
        body,
        count=1,
    )

    dst = HEADER + norm_fn + "\n\n" + body + EXTRA_FUNCTIONS
    DST.write_text(dst, encoding="utf-8")
    print(f"Wrote {DST} ({len(dst)} bytes)")


if __name__ == "__main__":
    main()
