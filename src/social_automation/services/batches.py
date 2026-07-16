"""Operazioni batch per API."""

from __future__ import annotations

import os
from typing import Any

from social_automation.db.store import (
    finalize_batch,
    get_batch,
    list_batch_items,
    list_batches,
    request_batch_stop,
)


def _pid_alive(pid: Any) -> bool:
    if pid is None:
        return False
    try:
        p = int(pid)
    except (TypeError, ValueError):
        return False
    if p <= 0:
        return False
    try:
        os.kill(p, 0)
        return True
    except OSError:
        return False


def reconcile_stale_running_batches(db_path) -> int:
    """
    Chiude batch ``running`` abbandonati.

    Con queue Vercel, ``runner_pid`` non è usato: un batch running con item
    ``queued``/``running`` è considerato attivo.
    """
    from social_automation.db.store import list_batch_items

    rows = list_batches(db_path, status="running", limit=100)
    closed = 0
    for row in rows:
        batch_id = int(row["id"])
        if _pid_alive(row.get("runner_pid")):
            continue
        items = list_batch_items(db_path, batch_id=batch_id, limit=10_000)
        active_statuses = {"queued", "running"}
        if any(str(i.get("status") or "").lower() in active_statuses for i in items):
            continue
        completed = int(row.get("completed_count") or 0)
        failed = int(row.get("failed_count") or 0)
        requested = max(1, int(row.get("requested_count") or 0))
        if completed + failed >= requested:
            status = "completed" if failed == 0 else ("partial" if completed > 0 else "failed")
        elif completed > 0:
            status = "partial"
        else:
            status = "failed"
        pid = row.get("runner_pid")
        if pid:
            reason = f"Runner terminato (PID {pid}) senza chiusura batch"
        else:
            reason = "Batch abbandonato: nessun item in coda"
        finalize_batch(
            db_path,
            batch_id=batch_id,
            status=status,
            completed_count=completed,
            failed_count=failed,
            last_error=reason,
        )
        closed += 1
    return closed


def serialize_batch(row: dict[str, Any]) -> dict[str, Any]:
    requested = int(row.get("requested_count", 0) or 0)
    completed = int(row.get("completed_count", 0) or 0)
    failed = int(row.get("failed_count", 0) or 0)
    done = completed + failed
    progress_pct = int((done / requested) * 100) if requested > 0 else 0
    return {
        "id": int(row["id"]),
        "status": str(row.get("status") or ""),
        "category": row.get("category"),
        "platform": row.get("platform"),
        "media_format": row.get("media_format"),
        "requested_count": requested,
        "completed_count": completed,
        "failed_count": failed,
        "done_count": done,
        "progress_pct": progress_pct,
        "started_at": str(row.get("started_at") or ""),
        "finished_at": str(row.get("finished_at") or ""),
        "runner_pid": row.get("runner_pid"),
        "stop_requested_at": row.get("stop_requested_at"),
        "stop_reason": row.get("stop_reason"),
        "last_error": row.get("last_error"),
        "note": row.get("note"),
        "updated_at": str(row.get("updated_at") or ""),
    }


def serialize_batch_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "batch_id": int(row["batch_id"]),
        "item_index": int(row.get("item_index") or 0),
        "status": str(row.get("status") or ""),
        "source_asset_id": row.get("source_asset_id"),
        "source_asset_name": row.get("source_asset_name"),
        "business_category": row.get("business_category"),
        "image_id": row.get("image_id"),
        "rendered_file": row.get("rendered_file"),
        "error_message": row.get("error_message"),
        "media_format": row.get("media_format"),
        "created_at": str(row.get("created_at") or ""),
    }


def get_batch_detail(db_path, *, batch_id: int) -> dict[str, Any] | None:
    row = get_batch(db_path, batch_id=batch_id)
    if row is None:
        return None
    items = list_batch_items(db_path, batch_id=batch_id, limit=5000)
    return {
        "batch": serialize_batch(row),
        "items": [serialize_batch_item(i) for i in items],
    }


def get_active_running_batch(db_path) -> dict[str, Any] | None:
    reconcile_stale_running_batches(db_path)
    rows = list_batches(db_path, status="running", limit=1)
    if not rows:
        return None
    return serialize_batch(rows[0])


def list_batches_filtered(
    db_path,
    *,
    status: str | None = None,
    platform=None,
    media_format=None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = list_batches(
        db_path,
        status=status,
        platform=platform,
        media_format=media_format,
        limit=max(1, min(200, int(limit))),
    )
    return [serialize_batch(r) for r in rows]


def stop_batch(db_path, *, batch_id: int, reason: str | None = None) -> bool:
    return request_batch_stop(db_path, batch_id=batch_id, reason=reason)
