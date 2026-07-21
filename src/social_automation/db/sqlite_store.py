"""Persistenza locale SQLite per stato render, metadati e storico pianificazione."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from social_automation.app_timezone import query_datetime_utc, scheduled_for_db_iso
from social_automation.models import MediaFormat, Platform

_LOG = logging.getLogger(__name__)


def _normalize_media_format(media_format: MediaFormat | str | None) -> str:
    if media_format is None:
        return MediaFormat.POST.value
    if isinstance(media_format, MediaFormat):
        return media_format.value
    raw = str(media_format).strip().lower()
    if raw in {MediaFormat.POST.value, MediaFormat.STORY.value}:
        return raw
    return MediaFormat.POST.value


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(r["name"]) for r in rows}


def _create_images_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            render_ig INTEGER NOT NULL DEFAULT 0,
            render_fb INTEGER NOT NULL DEFAULT 0,
            render_ig_story INTEGER NOT NULL DEFAULT 0,
            render_fb_story INTEGER NOT NULL DEFAULT 0,
            is_valid_by_quality_evaluation INTEGER NULL,
            quality_predicted_class TEXT NULL,
            quality_predicted_confidence REAL NULL,
            is_valid_for_publication INTEGER NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _create_planning_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS planning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            event_type TEXT NOT NULL,
            scheduled_for TEXT NULL,
            external_id TEXT NULL,
            detail TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
        );
        """
    )


def _create_story_schedule_rules_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_schedule_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            schedule_mode TEXT NOT NULL,
            scheduled_for TEXT NULL,
            weekday INTEGER NULL,
            time_local TEXT NULL,
            timezone TEXT NOT NULL DEFAULT 'Europe/Rome',
            active INTEGER NOT NULL DEFAULT 1,
            detail TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_schedule_rules_active_mode
        ON story_schedule_rules(active, schedule_mode)
        """
    )


def _create_story_schedule_occurrences_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_schedule_occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            occurrence_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(rule_id) REFERENCES story_schedule_rules(id) ON DELETE CASCADE,
            UNIQUE(rule_id, occurrence_date)
        );
        """
    )


def _create_batches_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            category TEXT NULL,
            platform TEXT NULL,
            requested_count INTEGER NOT NULL DEFAULT 1,
            completed_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT NULL,
            runner_pid INTEGER NULL,
            last_error TEXT NULL,
            note TEXT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_batches_status_created_at
        ON batches(status, created_at DESC)
        """
    )


def _create_batch_items_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            item_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            source_asset_id TEXT NULL,
            source_asset_name TEXT NULL,
            business_category TEXT NULL,
            template_id TEXT NULL,
            image_id INTEGER NULL,
            rendered_file TEXT NULL,
            error_message TEXT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE CASCADE,
            FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE SET NULL
        );
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_items_batch_item_index
        ON batch_items(batch_id, item_index)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_batch_items_batch_status
        ON batch_items(batch_id, status, created_at DESC)
        """
    )


def _migrate_images_drop_redundant_planned_cols(conn: sqlite3.Connection) -> None:
    tables = {
        str(r["name"])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "images" not in tables:
        _create_images_table(conn)
        return
    cols = _table_columns(conn, "images")
    if "planned_on_ig" not in cols and "planned_on_fb" not in cols:
        return

    # Migrazione schema: rimuove planned_on_* da images e converte valori in planning_events.
    conn.execute("ALTER TABLE images RENAME TO images_old")
    _create_images_table(conn)
    _create_planning_events_table(conn)
    conn.execute(
        """
        INSERT INTO images(id, name, path, render_ig, render_fb, created_at, updated_at)
        SELECT
            id,
            name,
            path,
            COALESCE(render_ig, 0),
            COALESCE(render_fb, 0),
            COALESCE(created_at, datetime('now')),
            COALESCE(updated_at, datetime('now'))
        FROM images_old
        """
    )
    conn.execute(
        """
        INSERT INTO planning_events(image_id, platform, event_type, scheduled_for, detail)
        SELECT
            id,
            'instagram',
            'planned',
            planned_on_ig,
            'migrated_from_images.planned_on_ig'
        FROM images_old
        WHERE planned_on_ig IS NOT NULL AND TRIM(planned_on_ig) <> ''
        """
    )
    conn.execute(
        """
        INSERT INTO planning_events(image_id, platform, event_type, scheduled_for, detail)
        SELECT
            id,
            'facebook',
            'planned',
            planned_on_fb,
            'migrated_from_images.planned_on_fb'
        FROM images_old
        WHERE planned_on_fb IS NOT NULL AND TRIM(planned_on_fb) <> ''
        """
    )
    conn.execute("DROP TABLE images_old")


def ensure_db_schema(db_path: Path) -> None:
    with _connect(db_path) as conn:
        _migrate_images_drop_redundant_planned_cols(conn)
        _create_images_table(conn)
        _create_planning_events_table(conn)
        _create_story_schedule_rules_table(conn)
        _create_story_schedule_occurrences_table(conn)
        _create_batches_table(conn)
        _create_batch_items_table(conn)
        image_cols = _table_columns(conn, "images")
        if "render_ig_story" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN render_ig_story INTEGER NOT NULL DEFAULT 0"
            )
        if "render_fb_story" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN render_fb_story INTEGER NOT NULL DEFAULT 0"
            )
        if "is_valid_by_quality_evaluation" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN is_valid_by_quality_evaluation INTEGER NULL"
            )
        if "quality_predicted_class" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN quality_predicted_class TEXT NULL")
        if "quality_predicted_confidence" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN quality_predicted_confidence REAL NULL"
            )
        if "is_valid_for_publication" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN is_valid_for_publication INTEGER NULL"
            )
        if "vision_eval_pass" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN vision_eval_pass INTEGER NULL")
        if "vision_eval_reason" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN vision_eval_reason TEXT NULL")
        if "copy_json" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN copy_json TEXT NULL")
        if "retouch_json" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN retouch_json TEXT NULL")
        if "generated_image_path" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN generated_image_path TEXT NULL")
        if "visual_score" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN visual_score REAL NULL")
        if "visual_status" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN visual_status TEXT NULL")
        if "editing_required" not in image_cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN editing_required INTEGER NULL"
            )
        if "original_path" not in image_cols:
            conn.execute("ALTER TABLE images ADD COLUMN original_path TEXT NULL")
        batch_cols = _table_columns(conn, "batches")
        if "runner_pid" not in batch_cols:
            conn.execute("ALTER TABLE batches ADD COLUMN runner_pid INTEGER NULL")
        if "stop_requested_at" not in batch_cols:
            conn.execute("ALTER TABLE batches ADD COLUMN stop_requested_at TEXT NULL")
        if "stop_reason" not in batch_cols:
            conn.execute("ALTER TABLE batches ADD COLUMN stop_reason TEXT NULL")
        if "media_format" not in batch_cols:
            conn.execute("ALTER TABLE batches ADD COLUMN media_format TEXT NULL")
        item_cols = _table_columns(conn, "batch_items")
        if "media_format" not in item_cols:
            conn.execute("ALTER TABLE batch_items ADD COLUMN media_format TEXT NULL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER NOT NULL,
                platform TEXT NULL,
                template_id TEXT NULL,
                template_dimensions_source TEXT NULL,
                canvas_width INTEGER NULL,
                canvas_height INTEGER NULL,
                export_width INTEGER NULL,
                export_height INTEGER NULL,
                image_fit TEXT NULL,
                asset_id TEXT NULL,
                design_id TEXT NULL,
                source_file TEXT NULL,
                output_file TEXT NULL,
                mode TEXT NULL,
                note TEXT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
            );
            """
        )
        cols = _table_columns(conn, "metadata")
        if "source_asset_id" not in cols:
            conn.execute("ALTER TABLE metadata ADD COLUMN source_asset_id TEXT NULL")
        if "source_asset_name" not in cols:
            conn.execute("ALTER TABLE metadata ADD COLUMN source_asset_name TEXT NULL")
        if "business_category" not in cols:
            conn.execute("ALTER TABLE metadata ADD COLUMN business_category TEXT NULL")
        if "media_format" not in cols:
            conn.execute("ALTER TABLE metadata ADD COLUMN media_format TEXT NULL")


def _upsert_image(conn: sqlite3.Connection, *, name: str, path: str) -> int:
    existing = conn.execute("SELECT id FROM images WHERE path = ?", (path,)).fetchone()
    if existing:
        image_id = int(existing["id"])
        conn.execute(
            """
            UPDATE images
            SET name = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (name, image_id),
        )
        return image_id
    cur = conn.execute(
        "INSERT INTO images(name, path) VALUES(?, ?)",
        (name, path),
    )
    return int(cur.lastrowid)


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


_IMAGE_RENDER_FLAG_BY_KEY: dict[tuple[str, str], str] = {
    (Platform.INSTAGRAM.value, MediaFormat.POST.value): "render_ig",
    (Platform.FACEBOOK.value, MediaFormat.POST.value): "render_fb",
    (Platform.INSTAGRAM.value, MediaFormat.STORY.value): "render_ig_story",
    (Platform.FACEBOOK.value, MediaFormat.STORY.value): "render_fb_story",
}


def record_render_artifacts(
    db_path: Path,
    *,
    image_name: str,
    image_path: Path,
    source_asset_id: str | None = None,
    source_asset_name: str | None = None,
    business_category: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
    metadata_path: Path | None = None,
) -> int:
    """Registra/aggiorna tabella images e inserisce uno snapshot in metadata.

    ``metadata_payload`` può includere ``media_format`` (post|story) per distinguere
    i render delle storie dai post: il flag ``render_*_story`` viene aggiornato di
    conseguenza.
    """
    ensure_db_schema(db_path)
    payload: dict[str, Any] = dict(metadata_payload or {})
    if not payload and metadata_path is not None and metadata_path.is_file():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except ValueError:
            payload = {}

    media_format_value = _normalize_media_format(payload.get("media_format"))

    with _connect(db_path) as conn:
        image_id = _upsert_image(
            conn,
            name=image_name.strip() or image_path.name,
            path=str(image_path),
        )
        platform = str(payload.get("platform", "")).strip().lower()
        flag_col = _IMAGE_RENDER_FLAG_BY_KEY.get((platform, media_format_value))
        if flag_col:
            conn.execute(
                f"UPDATE images SET {flag_col} = 1, updated_at = datetime('now') WHERE id = ?",
                (image_id,),
            )

        conn.execute(
            """
            INSERT INTO metadata(
                image_id,
                platform,
                template_id,
                template_dimensions_source,
                canvas_width,
                canvas_height,
                export_width,
                export_height,
                image_fit,
                asset_id,
                design_id,
                source_file,
                output_file,
                mode,
                note,
                metadata_json,
                source_asset_id,
                source_asset_name,
                business_category,
                media_format
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_id,
                payload.get("platform"),
                payload.get("template_id"),
                payload.get("template_dimensions_source"),
                _int_or_none(payload.get("canvas_width")),
                _int_or_none(payload.get("canvas_height")),
                _int_or_none(payload.get("export_width")),
                _int_or_none(payload.get("export_height")),
                payload.get("image_fit"),
                payload.get("asset_id"),
                payload.get("design_id"),
                payload.get("source_file"),
                payload.get("output_file"),
                payload.get("mode"),
                payload.get("note"),
                json.dumps(payload, ensure_ascii=True),
                (source_asset_id or "").strip() or None,
                (source_asset_name or "").strip() or None,
                (business_category or "").strip().lower() or None,
                media_format_value,
            ),
        )
        return image_id


def _parse_json_col(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def record_processed_artifacts(
    db_path: Path,
    *,
    image_name: str,
    image_path: Path,
    source_asset_id: str | None = None,
    source_asset_name: str | None = None,
    business_category: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
    metadata_path: Path | None = None,
    retouch_json: dict[str, Any] | None = None,
    copy_json: dict[str, Any] | None = None,
    original_path: str | None = None,
    generated_image_path: str | None = None,
    visual_score: float | None = None,
    visual_status: str | None = None,
    editing_required: bool | None = None,
) -> int:
    """Registra foto processata (Story AI + Pillow) senza valutazione ONNX."""
    ensure_db_schema(db_path)
    payload: dict[str, Any] = dict(metadata_payload or {})
    if not payload and metadata_path is not None and metadata_path.is_file():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except ValueError:
            payload = {}

    media_format_value = _normalize_media_format(payload.get("media_format"))

    with _connect(db_path) as conn:
        image_id = _upsert_image(
            conn,
            name=image_name.strip() or image_path.name,
            path=str(image_path),
        )
        platform = str(payload.get("platform", "")).strip().lower()
        flag_col = _IMAGE_RENDER_FLAG_BY_KEY.get((platform, media_format_value))
        if flag_col:
            conn.execute(
                f"UPDATE images SET {flag_col} = 1, updated_at = datetime('now') WHERE id = ?",
                (image_id,),
            )

        retouch_text = json.dumps(retouch_json, ensure_ascii=False) if retouch_json else None
        copy_text = json.dumps(copy_json, ensure_ascii=False) if copy_json else None
        if retouch_text or copy_text:
            conn.execute(
                """
                UPDATE images
                SET retouch_json = COALESCE(?, retouch_json),
                    copy_json = COALESCE(?, copy_json),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (retouch_text, copy_text, image_id),
            )

        conn.execute(
            """
            UPDATE images
            SET original_path = COALESCE(?, original_path),
                generated_image_path = COALESCE(?, generated_image_path),
                visual_score = COALESCE(?, visual_score),
                visual_status = COALESCE(?, visual_status),
                editing_required = COALESCE(?, editing_required),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                (original_path or "").strip() or None,
                (generated_image_path or "").strip() or None,
                float(visual_score) if visual_score is not None else None,
                (visual_status or "").strip() or None,
                int(editing_required) if editing_required is not None else None,
                image_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO metadata(
                image_id,
                platform,
                template_id,
                template_dimensions_source,
                canvas_width,
                canvas_height,
                export_width,
                export_height,
                image_fit,
                asset_id,
                design_id,
                source_file,
                output_file,
                mode,
                note,
                metadata_json,
                source_asset_id,
                source_asset_name,
                business_category,
                media_format
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                image_id,
                payload.get("platform"),
                payload.get("template_id"),
                payload.get("template_dimensions_source"),
                _int_or_none(payload.get("canvas_width")),
                _int_or_none(payload.get("canvas_height")),
                _int_or_none(payload.get("export_width")),
                _int_or_none(payload.get("export_height")),
                payload.get("image_fit"),
                payload.get("asset_id"),
                payload.get("design_id"),
                payload.get("source_file"),
                payload.get("output_file"),
                payload.get("mode"),
                payload.get("note"),
                json.dumps(payload, ensure_ascii=True),
                (source_asset_id or "").strip() or None,
                (source_asset_name or "").strip() or None,
                (business_category or "").strip().lower() or None,
                media_format_value,
            ),
        )
        return image_id


def get_copy_pack(db_path: Path, *, image_id: int) -> dict[str, Any] | None:
    """Ultimo copy pack Story AI salvato su ``images.copy_json``."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT copy_json FROM images WHERE id = ?",
            (int(image_id),),
        ).fetchone()
    if not row:
        return None
    return _parse_json_col(row["copy_json"])


def get_image_record(db_path: Path, *, image_id: int) -> dict[str, Any] | None:
    """Riga ``images`` per id (path, copy, visual, ecc.)."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, name, path, copy_json, retouch_json, visual_score, visual_status,
                   editing_required, original_path, generated_image_path,
                   is_valid_for_publication, created_at, updated_at
            FROM images WHERE id = ?
            """,
            (int(image_id),),
        ).fetchone()
    return dict(row) if row is not None else None


def update_image_media_paths(
    db_path: Path,
    *,
    image_id: int,
    path: str | None = None,
    original_path: str | None = None,
    generated_image_path: str | None = None,
) -> None:
    """Aggiorna path/URL media dopo upload su Blob."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE images
            SET path = COALESCE(?, path),
                original_path = COALESCE(?, original_path),
                generated_image_path = COALESCE(?, generated_image_path),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                (path or "").strip() or None,
                (original_path or "").strip() or None,
                (generated_image_path or "").strip() or None,
                int(image_id),
            ),
        )


def update_image_copy_json(
    db_path: Path,
    *,
    image_id: int,
    copy_json: dict[str, Any],
) -> None:
    """Salva o sovrascrive il copy pack su ``images.copy_json``."""
    ensure_db_schema(db_path)
    text = json.dumps(copy_json, ensure_ascii=False)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE images
            SET copy_json = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (text, int(image_id)),
        )


def update_image_visual_state(
    db_path: Path,
    *,
    image_id: int,
    visual_status: str | None = None,
    editing_required: bool | None = None,
) -> None:
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE images
            SET visual_status = COALESCE(?, visual_status),
                editing_required = COALESCE(?, editing_required),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                (visual_status or "").strip() or None,
                int(editing_required) if editing_required is not None else None,
                int(image_id),
            ),
        )


def _visual_output_sql_predicate(alias: str = "i") -> str:
    """Immagine elaborata da Visual Producer (senza richiedere copy)."""
    a = alias
    return (
        f"({a}.visual_score IS NOT NULL OR "
        f"({a}.retouch_json IS NOT NULL AND TRIM(COALESCE({a}.retouch_json, '')) <> ''))"
    )


def delete_pending_approval_images(db_path: Path) -> int:
    """Elimina dal DB le immagini in coda approvazione (``is_valid_for_publication IS NULL``)."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM images WHERE is_valid_for_publication IS NULL")
        return int(cur.rowcount)


def list_ai_output_images(
    db_path: Path,
    *,
    approval_filter: str = "all",
    limit: int = 48,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Immagini elaborate da Story AI (output visual, copy opzionale)."""
    ensure_db_schema(db_path)
    lim = max(1, int(limit))
    off = max(0, int(offset))
    sql = """
    SELECT
        i.id,
        i.name,
        i.path,
        i.copy_json,
        i.retouch_json,
        i.visual_score,
        i.visual_status,
        i.editing_required,
        i.generated_image_path,
        i.original_path,
        i.is_valid_for_publication,
        i.created_at,
        i.updated_at,
        (
            SELECT m.source_file
            FROM metadata m
            WHERE m.image_id = i.id
            ORDER BY m.id DESC
            LIMIT 1
        ) AS source_file,
        (
            SELECT m.business_category
            FROM metadata m
            WHERE m.image_id = i.id
            ORDER BY m.id DESC
            LIMIT 1
        ) AS business_category
    FROM images i
    WHERE """
    sql += _visual_output_sql_predicate("i")
    params: list[Any] = []
    filt = (approval_filter or "all").strip().lower()
    if filt == "pending":
        sql += " AND i.is_valid_for_publication IS NULL"
    elif filt == "approved":
        sql += " AND i.is_valid_for_publication = 1"
    elif filt == "rejected":
        sql += " AND i.is_valid_for_publication = 0"
    sql += " ORDER BY i.id DESC LIMIT ? OFFSET ?"
    params.extend([lim, off])
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def count_ai_output_images(
    db_path: Path,
    *,
    approval_filter: str = "all",
) -> int:
    ensure_db_schema(db_path)
    sql = f"""
    SELECT COUNT(*) FROM images i
    WHERE {_visual_output_sql_predicate("i")}
    """
    params: list[Any] = []
    filt = (approval_filter or "all").strip().lower()
    if filt == "pending":
        sql += " AND i.is_valid_for_publication IS NULL"
    elif filt == "approved":
        sql += " AND i.is_valid_for_publication = 1"
    elif filt == "rejected":
        sql += " AND i.is_valid_for_publication = 0"
    with _connect(db_path) as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0]) if row else 0


def count_running_batches(db_path: Path) -> int:
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM batches WHERE status = 'running'"
        ).fetchone()
    return int(row[0]) if row else 0


def backfill_image_quality_evaluations(
    db_path: Path,
    *,
    limit: int = 500,
    offset: int = 0,
    only_unscored: bool = True,
) -> dict[str, int]:
    """
    Ricalcola valutazione qualità (flag, classe predetta, confidenza) per righe ``images``.

    Restituisce conteggi ``{"updated": n, "skipped": n, "errors": n}``.
    """
    from social_automation.image_quality_onnx import evaluate_image_quality, quality_gate_configured
    from social_automation.settings import load_settings

    s = load_settings()
    if not quality_gate_configured(s):
        raise ValueError(
            "Modello qualità non configurato: imposta IMAGE_QUALITY_ONNX_PATH e "
            "IMAGE_QUALITY_CLASS_NAMES_PATH (file esistenti) e installa onnxruntime."
        )
    ensure_db_schema(db_path)
    lim = max(1, int(limit))
    off = max(0, int(offset))
    sql = "SELECT id, path FROM images"
    params: list[Any] = []
    if only_unscored:
        sql += " WHERE quality_predicted_class IS NULL"
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([lim, off])
    updated = 0
    skipped = 0
    errors = 0
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        for r in rows:
            iid = int(r["id"])
            p = Path(str(r["path"]))
            if not p.is_file():
                skipped += 1
                continue
            try:
                val = evaluate_image_quality(p, s)
            except Exception:
                errors += 1
                continue
            if val is None:
                skipped += 1
                continue
            conn.execute(
                """
                UPDATE images
                SET is_valid_by_quality_evaluation = ?,
                    quality_predicted_class = ?,
                    quality_predicted_confidence = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    int(val.is_valid_by_quality_evaluation),
                    str(val.predicted_class),
                    float(val.predicted_confidence),
                    iid,
                ),
            )
            updated += 1
    return {"updated": updated, "skipped": skipped, "errors": errors}


def has_source_asset_render_for_platform(
    db_path: Path,
    *,
    source_asset_id: str,
    platform: Platform,
    media_format: MediaFormat | str = MediaFormat.POST,
) -> bool:
    """True se esiste già un render registrato per source asset/piattaforma/formato.

    Per le storie (``media_format = story``) IG e FB sono tracciati separatamente
    anche se condividono lo stesso template/cartella di output.
    """
    ensure_db_schema(db_path)
    sid = source_asset_id.strip()
    if not sid:
        return False
    fmt = _normalize_media_format(media_format)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM metadata
            WHERE source_asset_id = ?
              AND platform = ?
              AND COALESCE(media_format, ?) = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (sid, platform.value, MediaFormat.POST.value, fmt),
        ).fetchone()
    return row is not None


def latest_metadata_for_image(
    db_path: Path,
    *,
    image_id: int,
) -> dict[str, Any] | None:
    """Ultima riga metadata per una image (utile per rerender da sorgente Drive)."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
              id,
              image_id,
              platform,
              template_id,
              source_asset_id,
              source_asset_name,
              business_category,
              source_file,
              media_format,
              metadata_json,
              created_at
            FROM metadata
            WHERE image_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (image_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def latest_plan_for_image(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform | None = None,
) -> dict[str, Any] | None:
    """Restituisce l'ultimo evento di planning per image (e opzionalmente piattaforma)."""
    ensure_db_schema(db_path)
    sql = (
        "SELECT id, image_id, platform, event_type, scheduled_for, external_id, detail, created_at "
        "FROM planning_events WHERE image_id = ?"
    )
    params: list[Any] = [image_id]
    if platform is not None:
        sql += " AND platform = ?"
        params.append(platform.value)
    sql += " ORDER BY id DESC LIMIT 1"
    with _connect(db_path) as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    if row is None:
        return None
    return dict(row)


def list_pending_events(
    db_path: Path,
    *,
    platform: Platform | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lista eventi pending (ultimo stato planned/rescheduled per image+platform)."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    query = """
    WITH ranked AS (
      SELECT
        p.*,
        ROW_NUMBER() OVER (
          PARTITION BY p.image_id, p.platform
          ORDER BY p.id DESC
        ) AS rn
      FROM planning_events p
    )
    SELECT
      r.id,
      r.image_id,
      i.name AS image_name,
      i.path AS image_path,
      r.platform,
      r.event_type,
      r.scheduled_for,
      r.external_id,
      r.detail,
      r.created_at
    FROM ranked r
    JOIN images i ON i.id = r.image_id
    WHERE r.rn = 1
      AND r.event_type IN ('planned', 'rescheduled')
    """
    params: list[Any] = []
    if platform is not None:
        query += " AND r.platform = ?"
        params.append(platform.value)
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(max_rows)
    with _connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def list_due_events(
    db_path: Path,
    *,
    due_before: datetime,
    platform: Platform | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Eventi pianificati scaduti (ultimo stato planned/rescheduled per image+platform)."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    due_iso = query_datetime_utc(due_before).isoformat()
    query = """
    WITH ranked AS (
      SELECT
        p.*,
        ROW_NUMBER() OVER (
          PARTITION BY p.image_id, p.platform
          ORDER BY p.id DESC
        ) AS rn
      FROM planning_events p
      WHERE p.scheduled_for IS NOT NULL
    )
    SELECT
      r.id,
      r.image_id,
      i.name AS image_name,
      i.path AS image_path,
      r.platform,
      r.event_type,
      r.scheduled_for,
      r.external_id,
      r.detail,
      r.created_at,
      i.is_valid_by_quality_evaluation,
      i.is_valid_for_publication,
      i.vision_eval_pass,
      i.vision_eval_reason,
      i.copy_json
    FROM ranked r
    JOIN images i ON i.id = r.image_id
    WHERE r.rn = 1
      AND r.event_type IN ('planned', 'rescheduled')
      AND julianday(r.scheduled_for) <= julianday(?)
      AND (r.external_id IS NULL OR TRIM(COALESCE(r.external_id, '')) = '')
    """
    params: list[Any] = [due_iso]
    if platform is not None:
        query += " AND r.platform = ?"
        params.append(platform.value)
    query += " ORDER BY r.scheduled_for ASC, r.id ASC LIMIT ?"
    params.append(max_rows)
    with _connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def list_calendar_items(
    db_path: Path,
    *,
    start_inclusive: datetime,
    end_exclusive: datetime,
    platform: Platform | None = None,
    business_category: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Eventi pianificati correnti in una finestra temporale (per calendario FE)."""
    ensure_db_schema(db_path)
    start_iso = query_datetime_utc(start_inclusive).isoformat()
    end_iso = query_datetime_utc(end_exclusive).isoformat()
    max_rows = max(1, int(limit))
    query = """
    WITH latest AS (
      SELECT
        p.*,
        ROW_NUMBER() OVER (
          PARTITION BY p.image_id, p.platform
          ORDER BY p.id DESC
        ) AS rn
      FROM planning_events p
      WHERE p.scheduled_for IS NOT NULL
    )
    SELECT
      l.id,
      l.image_id,
      i.name AS image_name,
      i.path AS image_path,
      l.platform,
      l.event_type,
      l.scheduled_for,
      l.external_id,
      l.detail,
      l.created_at
    FROM latest l
    JOIN images i ON i.id = l.image_id
    WHERE l.rn = 1
      AND l.event_type IN ('planned', 'rescheduled')
      AND l.scheduled_for >= ?
      AND l.scheduled_for < ?
    """
    params: list[Any] = [start_iso, end_iso]
    if platform is not None:
        query += " AND l.platform = ?"
        params.append(platform.value)
    category = (business_category or "").strip().lower()
    if category:
        query += """
      AND EXISTS (
        SELECT 1
        FROM metadata m
        WHERE m.image_id = l.image_id
          AND LOWER(COALESCE(m.business_category, '')) = ?
      )
        """
        params.append(category)
    query += """
    ORDER BY l.scheduled_for ASC
    LIMIT ?
    """
    params.append(max_rows)
    with _connect(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def _plannable_images_sql_filters(
    *,
    platform: Platform | None,
    fmt: str,
    business_category: str | None,
    require_quality_pass: bool,
    require_manual_publication_valid: bool,
) -> tuple[str, list[Any]]:
    """Frammento SQL (dopo ``WHERE 1=1``) e parametri per immagini pianificabili."""
    sql = ""
    params: list[Any] = []
    if fmt == MediaFormat.STORY.value:
        # Stesso asset story per IG e FB (cartella ``stories/`` condivisa).
        sql += " AND (render_ig_story = 1 OR render_fb_story = 1)"
    else:
        if platform == Platform.INSTAGRAM:
            sql += " AND render_ig = 1"
        elif platform == Platform.FACEBOOK:
            sql += " AND render_fb = 1"
    category = (business_category or "").strip().lower()
    if category:
        sql += (
            " AND EXISTS ("
            "SELECT 1 FROM metadata m "
            "WHERE m.image_id = images.id "
            "AND LOWER(COALESCE(m.business_category, '')) = ?"
            ")"
        )
        params.append(category)
    if require_quality_pass:
        sql += " AND is_valid_by_quality_evaluation = 1"
    if require_manual_publication_valid:
        sql += " AND is_valid_for_publication = 1"
    return sql, params


def count_plannable_images(
    db_path: Path,
    *,
    platform: Platform | None = None,
    business_category: str | None = None,
    media_format: MediaFormat | str = MediaFormat.POST,
    require_quality_pass: bool = False,
    require_manual_publication_valid: bool = False,
) -> int:
    """Conta immagini pianificabili (stessi filtri di ``list_plannable_images``)."""
    ensure_db_schema(db_path)
    fmt = _normalize_media_format(media_format)
    frag, params = _plannable_images_sql_filters(
        platform=platform,
        fmt=fmt,
        business_category=business_category,
        require_quality_pass=require_quality_pass,
        require_manual_publication_valid=require_manual_publication_valid,
    )
    sql = f"SELECT COUNT(*) FROM images WHERE 1=1{frag}"
    with _connect(db_path) as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0]) if row is not None else 0


def list_plannable_image_ids(
    db_path: Path,
    *,
    platform: Platform | None = None,
    business_category: str | None = None,
    media_format: MediaFormat | str = MediaFormat.POST,
    require_quality_pass: bool = False,
    require_manual_publication_valid: bool = False,
) -> list[int]:
    """Id immagini pianificabili (ordinati da id più recente), senza paginazione."""
    ensure_db_schema(db_path)
    fmt = _normalize_media_format(media_format)
    frag, params = _plannable_images_sql_filters(
        platform=platform,
        fmt=fmt,
        business_category=business_category,
        require_quality_pass=require_quality_pass,
        require_manual_publication_valid=require_manual_publication_valid,
    )
    sql = f"SELECT id FROM images WHERE 1=1{frag} ORDER BY id DESC"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [int(r[0]) for r in rows]


def get_images_by_ids(db_path: Path, image_ids: list[int]) -> list[dict[str, Any]]:
    """Righe ``images`` per gli id richiesti (stesso shape di ``list_plannable_images``)."""
    if not image_ids:
        return []
    ensure_db_schema(db_path)
    uniq: list[int] = []
    seen: set[int] = set()
    for raw in image_ids:
        i = int(raw)
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    placeholders = ",".join("?" * len(uniq))
    sql = (
        "SELECT id, name, path, render_ig, render_fb, render_ig_story, render_fb_story, "
        "is_valid_by_quality_evaluation, quality_predicted_class, quality_predicted_confidence, "
        "is_valid_for_publication, vision_eval_pass, vision_eval_reason, created_at, updated_at "
        "FROM images WHERE id IN ("
        f"{placeholders})"
    )
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(uniq)).fetchall()
    by_id = {int(r["id"]): dict(r) for r in rows}
    return [by_id[i] for i in image_ids if i in by_id]


def list_plannable_images(
    db_path: Path,
    *,
    platform: Platform | None = None,
    business_category: str | None = None,
    limit: int = 500,
    offset: int = 0,
    media_format: MediaFormat | str = MediaFormat.POST,
    require_quality_pass: bool = False,
    require_manual_publication_valid: bool = False,
) -> list[dict[str, Any]]:
    """Lista immagini renderizzate (filtrabili per piattaforma+formato) candidabili a planning."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    off = max(0, int(offset))
    fmt = _normalize_media_format(media_format)
    sql = (
        "SELECT id, name, path, render_ig, render_fb, render_ig_story, render_fb_story, "
        "is_valid_by_quality_evaluation, quality_predicted_class, quality_predicted_confidence, "
        "is_valid_for_publication, created_at, updated_at "
        "FROM images WHERE 1=1"
    )
    frag, params = _plannable_images_sql_filters(
        platform=platform,
        fmt=fmt,
        business_category=business_category,
        require_quality_pass=require_quality_pass,
        require_manual_publication_valid=require_manual_publication_valid,
    )
    sql += frag + " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([max_rows, off])
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def update_vision_eval(
    db_path: Path,
    *,
    image_id: int,
    vision_pass: int,
    reason: str | None = None,
) -> None:
    """Salva esito validazione vision brand su ``images``."""
    ensure_db_schema(db_path)
    if vision_pass not in {0, 1}:
        raise ValueError("vision_pass deve essere 0 o 1")
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE images
            SET vision_eval_pass = ?,
                vision_eval_reason = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (int(vision_pass), (reason or "").strip() or None, int(image_id)),
        )


def set_image_manual_publication_valid(
    db_path: Path,
    *,
    image_id: int,
    value: int | None,
) -> None:
    """
    Approvazione manuale per la pubblicazione in pianificazione.

    ``value``: ``1`` approvata, ``0`` respinta, ``None`` revoca (torna in sospeso).
    """
    ensure_db_schema(db_path)
    if value is not None and int(value) not in (0, 1):
        raise ValueError("is_valid_for_publication deve essere 0, 1 oppure None")
    iid = int(image_id)
    with _connect(db_path) as conn:
        if value is None:
            conn.execute(
                """
                UPDATE images
                SET is_valid_for_publication = NULL, updated_at = datetime('now')
                WHERE id = ?
                """,
                (iid,),
            )
        else:
            conn.execute(
                """
                UPDATE images
                SET is_valid_for_publication = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (int(value), iid),
            )


def count_images_for_manual_publication_review(
    db_path: Path,
    *,
    platform: Platform | None = None,
    business_category: str | None = None,
    media_format: MediaFormat | str = MediaFormat.POST,
    require_quality_pass: bool = False,
    pending_manual_only: bool = False,
    require_ai_output: bool = False,
) -> int:
    """Conta righe per la schermata di approvazione (stessi filtri della lista)."""
    ensure_db_schema(db_path)
    fmt = _normalize_media_format(media_format)
    frag, params = _plannable_images_sql_filters(
        platform=platform,
        fmt=fmt,
        business_category=business_category,
        require_quality_pass=require_quality_pass,
        require_manual_publication_valid=False,
    )
    if pending_manual_only:
        frag += " AND is_valid_for_publication IS NULL"
    if require_ai_output:
        frag += " AND copy_json IS NOT NULL AND TRIM(COALESCE(copy_json, '')) <> ''"
    sql = f"SELECT COUNT(*) FROM images WHERE 1=1{frag}"
    with _connect(db_path) as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return int(row[0]) if row is not None else 0


def list_images_for_manual_publication_review(
    db_path: Path,
    *,
    platform: Platform | None = None,
    business_category: str | None = None,
    media_format: MediaFormat | str = MediaFormat.POST,
    require_quality_pass: bool = False,
    pending_manual_only: bool = False,
    require_ai_output: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Immagini per la schermata di approvazione manuale (vedi ``pending_manual_only``)."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    off = max(0, int(offset))
    fmt = _normalize_media_format(media_format)
    sql = (
        "SELECT id, name, path, render_ig, render_fb, render_ig_story, render_fb_story, "
        "is_valid_by_quality_evaluation, quality_predicted_class, quality_predicted_confidence, "
        "is_valid_for_publication, copy_json, retouch_json, visual_score, visual_status, "
        "editing_required, generated_image_path, original_path, created_at, updated_at "
        "FROM images WHERE 1=1"
    )
    frag, params = _plannable_images_sql_filters(
        platform=platform,
        fmt=fmt,
        business_category=business_category,
        require_quality_pass=require_quality_pass,
        require_manual_publication_valid=False,
    )
    if pending_manual_only:
        frag += " AND is_valid_for_publication IS NULL"
    if require_ai_output:
        frag += " AND copy_json IS NOT NULL AND TRIM(COALESCE(copy_json, '')) <> ''"
    sql += frag + " ORDER BY id DESC LIMIT ? OFFSET ?"
    qparams = list(params)
    qparams.extend([max_rows, off])
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(qparams)).fetchall()
    return [dict(r) for r in rows]


def add_planning_event(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    event_type: str,
    scheduled_for: datetime | None = None,
    external_id: str | None = None,
    detail: str | None = None,
) -> int:
    """Inserisce un evento di pianificazione/pubblicazione (append-only). Restituisce ``id`` della riga."""
    ensure_db_schema(db_path)
    platform_value = platform.value
    event = event_type.strip().lower()
    if not event:
        raise ValueError("event_type non può essere vuoto")
    scheduled = scheduled_for_db_iso(scheduled_for)
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO planning_events(
                image_id,
                platform,
                event_type,
                scheduled_for,
                external_id,
                detail
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (image_id, platform_value, event, scheduled, external_id, detail),
        )
        return int(cur.lastrowid)


def update_planning_event_external_id(
    db_path: Path,
    *,
    event_id: int,
    external_id: str,
) -> None:
    """Aggiorna ``external_id`` (es. id post programmato su Meta) per una riga ``planning_events``."""
    ensure_db_schema(db_path)
    ext = (external_id or "").strip()
    if not ext:
        raise ValueError("external_id non può essere vuoto")
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE planning_events SET external_id = ? WHERE id = ?",
            (ext, int(event_id)),
        )


def _image_has_story_render(conn: sqlite3.Connection, image_id: int) -> bool:
    row = conn.execute(
        "SELECT render_ig_story, render_fb_story FROM images WHERE id = ?",
        (int(image_id),),
    ).fetchone()
    if row is None:
        return False
    return int(row["render_ig_story"] or 0) == 1 or int(row["render_fb_story"] or 0) == 1


def add_story_schedule_rule(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    schedule_mode: str,
    timezone_name: str,
    scheduled_for: datetime | None = None,
    weekday: int | None = None,
    time_local: str | None = None,
    detail: str | None = None,
) -> int:
    """Inserisce una regola di pubblicazione story (one-shot o settimanale)."""
    ensure_db_schema(db_path)
    mode = schedule_mode.strip().lower()
    if mode not in {"once", "weekly"}:
        raise ValueError("schedule_mode deve essere 'once' o 'weekly'")
    tz = (timezone_name or "").strip() or "Europe/Rome"
    try:
        ZoneInfo(tz)
    except Exception as e:
        raise ValueError(f"timezone non valido: {tz}") from e

    scheduled_iso: str | None = None
    wd: int | None = None
    tl: str | None = None
    if mode == "once":
        if scheduled_for is None:
            raise ValueError("scheduled_for obbligatorio per schedule_mode=once")
        if scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for deve essere timezone-aware (es. con ZoneInfo)")
        scheduled_iso = scheduled_for.isoformat()
    else:
        if weekday is None or weekday < 0 or weekday > 6:
            raise ValueError("weekday deve essere 0–6 (lun–dom) per schedule_mode=weekly")
        raw_tl = (time_local or "").strip()
        if not raw_tl:
            raise ValueError("time_local obbligatorio per schedule_mode=weekly (formato HH:MM)")
        parts = raw_tl.split(":")
        if len(parts) != 2:
            raise ValueError("time_local deve essere HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("time_local fuori range")
        wd = int(weekday)
        tl = f"{h:02d}:{m:02d}"

    with _connect(db_path) as conn:
        if not _image_has_story_render(conn, image_id):
            raise ValueError("L'immagine non ha un render story registrato (render_ig_story/render_fb_story).")
        cur = conn.execute(
            """
            INSERT INTO story_schedule_rules(
                image_id, platform, schedule_mode, scheduled_for, weekday, time_local, timezone, active, detail
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                int(image_id),
                platform.value,
                mode,
                scheduled_iso,
                wd,
                tl,
                tz,
                (detail or "").strip() or None,
            ),
        )
        return int(cur.lastrowid)


def list_story_schedule_rules(
    db_path: Path,
    *,
    active_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Elenco regole story con path immagine (per UI e manutenzione)."""
    ensure_db_schema(db_path)
    max_rows = max(1, min(int(limit), 2000))
    sql = """
    SELECT
      r.id,
      r.image_id,
      r.platform,
      r.schedule_mode,
      r.scheduled_for,
      r.weekday,
      r.time_local,
      r.timezone,
      r.active,
      r.detail,
      r.created_at,
      i.name AS image_name,
      i.path AS image_path
    FROM story_schedule_rules r
    JOIN images i ON i.id = r.image_id
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE r.active = 1"
    sql += " ORDER BY r.id DESC LIMIT ?"
    params.append(max_rows)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def set_story_schedule_rule_active(
    db_path: Path,
    *,
    rule_id: int,
    active: bool,
) -> None:
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE story_schedule_rules SET active = ? WHERE id = ?",
            (1 if active else 0, int(rule_id)),
        )


def reserve_story_occurrence_slot(
    db_path: Path,
    *,
    rule_id: int,
    occurrence_date: str,
) -> bool:
    """Prenota uno slot (dedupe atomico). True se la riga è stata inserita."""
    ensure_db_schema(db_path)
    key = occurrence_date.strip()
    if not key:
        raise ValueError("occurrence_date non può essere vuoto")
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO story_schedule_occurrences(rule_id, occurrence_date)
            VALUES (?, ?)
            """,
            (int(rule_id), key),
        )
        return cur.rowcount == 1


def delete_story_occurrence_slot(
    db_path: Path,
    *,
    rule_id: int,
    occurrence_date: str,
) -> None:
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM story_schedule_occurrences WHERE rule_id = ? AND occurrence_date = ?",
            (int(rule_id), occurrence_date.strip()),
        )


def story_occurrence_exists(
    db_path: Path,
    *,
    rule_id: int,
    occurrence_date: str,
) -> bool:
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM story_schedule_occurrences
            WHERE rule_id = ? AND occurrence_date = ?
            LIMIT 1
            """,
            (int(rule_id), occurrence_date.strip()),
        ).fetchone()
    return row is not None


def create_batch(
    db_path: Path,
    *,
    category: str,
    platform: Platform,
    requested_count: int,
    note: str | None = None,
    media_format: MediaFormat | str = MediaFormat.POST,
) -> int:
    """Crea una run batch con stato iniziale running."""
    ensure_db_schema(db_path)
    req = max(1, int(requested_count))
    fmt = _normalize_media_format(media_format)
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO batches(
                status,
                category,
                platform,
                requested_count,
                note,
                media_format
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "running",
                (category or "").strip().lower() or None,
                platform.value,
                req,
                (note or "").strip() or None,
                fmt,
            ),
        )
        return int(cur.lastrowid)


def add_batch_item(
    db_path: Path,
    *,
    batch_id: int,
    item_index: int,
    status: str,
    source_asset_id: str | None = None,
    source_asset_name: str | None = None,
    business_category: str | None = None,
    template_id: str | None = None,
    image_id: int | None = None,
    rendered_file: str | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
    media_format: MediaFormat | str | None = None,
) -> None:
    """Registra il risultato di un singolo item batch."""
    ensure_db_schema(db_path)
    item_status = (status or "").strip().lower()
    if not item_status:
        raise ValueError("status batch item non può essere vuoto")
    idx = max(1, int(item_index))
    body = dict(payload or {})
    fmt: str | None
    if media_format is None and "media_format" not in body:
        fmt = None
    else:
        fmt = _normalize_media_format(
            media_format if media_format is not None else body.get("media_format")
        )
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO batch_items(
                batch_id,
                item_index,
                status,
                source_asset_id,
                source_asset_name,
                business_category,
                template_id,
                image_id,
                rendered_file,
                error_message,
                payload_json,
                media_format
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(batch_id),
                idx,
                item_status,
                (source_asset_id or "").strip() or None,
                (source_asset_name or "").strip() or None,
                (business_category or "").strip().lower() or None,
                (template_id or "").strip() or None,
                _int_or_none(image_id),
                (rendered_file or "").strip() or None,
                (error_message or "").strip() or None,
                json.dumps(body, ensure_ascii=True),
                fmt,
            ),
        )


def finalize_batch(
    db_path: Path,
    *,
    batch_id: int,
    status: str,
    completed_count: int,
    failed_count: int,
    last_error: str | None = None,
    note: str | None = None,
) -> None:
    """Chiude una run batch aggiornando stato, contatori e timestamp finale."""
    ensure_db_schema(db_path)
    final_status = (status or "").strip().lower()
    if not final_status:
        raise ValueError("status batch finale non può essere vuoto")
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE batches
            SET
              status = ?,
              completed_count = ?,
              failed_count = ?,
              last_error = ?,
              note = COALESCE(?, note),
              finished_at = datetime('now'),
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                final_status,
                max(0, int(completed_count)),
                max(0, int(failed_count)),
                (last_error or "").strip() or None,
                (note or "").strip() or None,
                int(batch_id),
            ),
        )


def update_batch_progress(
    db_path: Path,
    *,
    batch_id: int,
    completed_count: int,
    failed_count: int,
    last_error: str | None = None,
    status: str = "running",
) -> None:
    """Aggiorna avanzamento batch durante l'esecuzione."""
    ensure_db_schema(db_path)
    run_status = (status or "").strip().lower() or "running"
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE batches
            SET
              status = ?,
              completed_count = ?,
              failed_count = ?,
              last_error = COALESCE(?, last_error),
              updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                run_status,
                max(0, int(completed_count)),
                max(0, int(failed_count)),
                (last_error or "").strip() or None,
                int(batch_id),
            ),
        )


def mark_batch_runner_pid(
    db_path: Path,
    *,
    batch_id: int,
    runner_pid: int | None,
) -> None:
    """Salva pid del processo che sta eseguendo il batch."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE batches
            SET runner_pid = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (_int_or_none(runner_pid), int(batch_id)),
        )


def request_batch_stop(
    db_path: Path,
    *,
    batch_id: int,
    reason: str | None = None,
) -> bool:
    """Richiede stop manuale per un batch running; ritorna True se richiesta salvata."""
    ensure_db_schema(db_path)
    msg = (reason or "").strip() or "Stop manuale richiesto da interfaccia utente."
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            UPDATE batches
            SET
              stop_requested_at = datetime('now'),
              stop_reason = ?,
              updated_at = datetime('now')
            WHERE id = ?
              AND status = 'running'
            """,
            (msg, int(batch_id)),
        )
        return int(cur.rowcount or 0) > 0


def get_batch_stop_message(db_path: Path, *, batch_id: int) -> str | None:
    """Restituisce messaggio stop se il batch running ha una richiesta di stop."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status, stop_requested_at, stop_reason
            FROM batches
            WHERE id = ?
            LIMIT 1
            """,
            (int(batch_id),),
        ).fetchone()
    if row is None:
        return None
    status = str(row["status"] or "").strip().lower()
    requested_at = str(row["stop_requested_at"] or "").strip()
    if status != "running" or not requested_at:
        return None
    reason = str(row["stop_reason"] or "").strip()
    if reason:
        return f"Batch interrotto manualmente: {reason}"
    return "Batch interrotto manualmente: richiesta di stop utente."


def get_batch(db_path: Path, *, batch_id: int) -> dict[str, Any] | None:
    """Recupera una singola run batch."""
    ensure_db_schema(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
              id,
              status,
              category,
              platform,
              media_format,
              requested_count,
              completed_count,
              failed_count,
              started_at,
              finished_at,
              runner_pid,
              stop_requested_at,
              stop_reason,
              last_error,
              note,
              created_at,
              updated_at
            FROM batches
            WHERE id = ?
            LIMIT 1
            """,
            (int(batch_id),),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_batches(
    db_path: Path,
    *,
    status: str | None = None,
    platform: Platform | None = None,
    limit: int = 100,
    media_format: MediaFormat | str | None = None,
) -> list[dict[str, Any]]:
    """Lista batch (ultimi prima), filtrabili per stato/piattaforma/formato."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    sql = (
        "SELECT id, status, category, platform, media_format, requested_count, "
        "completed_count, failed_count, started_at, finished_at, runner_pid, "
        "stop_requested_at, stop_reason, last_error, note, "
        "created_at, updated_at "
        "FROM batches WHERE 1=1"
    )
    params: list[Any] = []
    st_val = (status or "").strip().lower()
    if st_val:
        sql += " AND status = ?"
        params.append(st_val)
    if platform is not None:
        sql += " AND platform = ?"
        params.append(platform.value)
    if media_format is not None:
        sql += " AND COALESCE(media_format, ?) = ?"
        fmt = _normalize_media_format(media_format)
        params.append(MediaFormat.POST.value)
        params.append(fmt)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max_rows)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def list_batch_items(
    db_path: Path,
    *,
    batch_id: int,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Dettaglio item di un batch."""
    ensure_db_schema(db_path)
    max_rows = max(1, int(limit))
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              batch_id,
              item_index,
              status,
              source_asset_id,
              source_asset_name,
              business_category,
              template_id,
              image_id,
              rendered_file,
              error_message,
              payload_json,
              media_format,
              created_at
            FROM batch_items
            WHERE batch_id = ?
            ORDER BY item_index ASC
            LIMIT ?
            """,
            (int(batch_id), max_rows),
        ).fetchall()
    return [dict(r) for r in rows]


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
            """
        ).fetchone()
    return dict(row) if row else None

