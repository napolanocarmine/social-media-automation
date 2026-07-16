"""Processamento batch queue (1 item per invocazione cron)."""

from __future__ import annotations

import json
import logging
from typing import Any

from social_automation.db.store import (
    add_batch_item,
    finalize_batch,
    get_batch,
    get_batch_stop_message,
    get_next_queued_batch_item,
    update_batch_progress,
)
from social_automation.drive.client import DriveClient
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.workflow.process_photo import process_drive_asset

_LOG = logging.getLogger(__name__)


def _payload_dict(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def process_next_batch_item(settings: Settings) -> dict[str, Any]:
    db_path = settings.db_path
    item = get_next_queued_batch_item(db_path)
    if item is None:
        return {"message": "Nessun item in coda"}

    batch_id = int(item["batch_id"])
    item_index = int(item["item_index"])
    stop_msg = get_batch_stop_message(db_path, batch_id=batch_id)
    if stop_msg:
        finalize_batch(
            db_path,
            batch_id=batch_id,
            status="stopped",
            completed_count=int((get_batch(db_path, batch_id=batch_id) or {}).get("completed_count") or 0),
            failed_count=int((get_batch(db_path, batch_id=batch_id) or {}).get("failed_count") or 0),
            last_error=stop_msg,
        )
        return {"batch_id": batch_id, "status": "stopped", "message": stop_msg}

    batch = get_batch(db_path, batch_id=batch_id) or {}
    platform = Platform(str(batch.get("platform") or Platform.INSTAGRAM.value))
    media_format = MediaFormat(str(batch.get("media_format") or MediaFormat.POST.value))
    payload = _payload_dict(item)

    add_batch_item(
        db_path,
        batch_id=batch_id,
        item_index=item_index,
        status="running",
        source_asset_id=str(item.get("source_asset_id") or ""),
        source_asset_name=str(item.get("source_asset_name") or ""),
        business_category=str(item.get("business_category") or ""),
        payload=payload,
        media_format=media_format,
    )

    asset = DriveAsset(
        file_id=str(item.get("source_asset_id") or payload.get("file_id") or ""),
        name=str(item.get("source_asset_name") or payload.get("name") or ""),
        mime_type=str(payload.get("mime_type") or "image/jpeg"),
        category=payload.get("category"),
        path_segments=list(payload.get("path_segments") or []),
    )

    try:
        drive = DriveClient.from_settings(settings)
        out = process_drive_asset(
            asset,
            platform=platform,
            media_format=media_format,
            settings=settings,
            business_category=str(item.get("business_category") or payload.get("business_category") or ""),
            drive=drive,
            auto_approve=False,
            generate_copy=False,
            marketing_objectives=list(payload.get("marketing_objectives") or []),
            channels=[Platform(str(c)) for c in (payload.get("channels") or [])] or None,
        )
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=item_index,
            status="completed",
            source_asset_id=asset.file_id,
            source_asset_name=asset.name,
            business_category=str(item.get("business_category") or ""),
            image_id=int(out["image_id"]),
            rendered_file=str(out.get("processed_file") or out.get("blob_url") or ""),
            payload={**payload, "processed_file": str(out.get("processed_file") or "")},
            media_format=media_format,
        )
        completed = int(batch.get("completed_count") or 0) + 1
        failed = int(batch.get("failed_count") or 0)
        update_batch_progress(
            db_path,
            batch_id=batch_id,
            completed_count=completed,
            failed_count=failed,
            status="running",
        )
        _maybe_finalize_batch(db_path, batch_id=batch_id)
        return {
            "batch_id": batch_id,
            "item_index": item_index,
            "status": "completed",
            "image_id": int(out["image_id"]),
        }
    except Exception as exc:
        msg = str(exc).strip() or repr(exc)
        _LOG.exception("Batch item failed batch=%s item=%s: %s", batch_id, item_index, msg)
        failed = int(batch.get("failed_count") or 0) + 1
        completed = int(batch.get("completed_count") or 0)
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=item_index,
            status="failed",
            source_asset_id=asset.file_id,
            source_asset_name=asset.name,
            error_message=msg,
            payload=payload,
            media_format=media_format,
        )
        update_batch_progress(
            db_path,
            batch_id=batch_id,
            completed_count=completed,
            failed_count=failed,
            last_error=msg,
            status="failed",
        )
        finalize_batch(
            db_path,
            batch_id=batch_id,
            status="failed",
            completed_count=completed,
            failed_count=failed,
            last_error=msg,
        )
        return {"batch_id": batch_id, "item_index": item_index, "status": "failed", "error": msg}


def _maybe_finalize_batch(db_path, *, batch_id: int) -> None:
    from social_automation.db.store import list_batch_items

    items = list_batch_items(db_path, batch_id=batch_id, limit=10_000)
    if not items:
        return
    terminal = {"completed", "failed", "cancelled"}
    if all(str(i.get("status") or "").lower() in terminal for i in items):
        batch = get_batch(db_path, batch_id=batch_id) or {}
        failed = sum(1 for i in items if str(i.get("status")).lower() == "failed")
        completed = sum(1 for i in items if str(i.get("status")).lower() == "completed")
        status = "completed" if failed == 0 else "failed"
        finalize_batch(
            db_path,
            batch_id=batch_id,
            status=status,
            completed_count=completed,
            failed_count=failed,
            last_error=str(batch.get("last_error") or "") or None,
        )
