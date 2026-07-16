"""Batch Story AI su asset Drive selezionati dall'utente (coda esplicita)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from social_automation.db.store import (
    add_batch_item,
    finalize_batch,
    get_batch,
    get_batch_stop_message,
    update_batch_progress,
)
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import normalize_business_category
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.settings import load_settings
from social_automation.visual.batch_revised_prompt_log import (
    append_batch_revised_prompt_log,
    revised_prompt_from_process_output,
)
from social_automation.workflow.process_photo import process_drive_asset


def run_selected_ai_batch(*, batch_id: int, queue_file: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    db_path = settings.db_path
    finalized = False
    try:
        _run_selected_ai_batch_body(
            batch_id=batch_id,
            queue_file=queue_file,
            settings=settings,
            db_path=db_path,
        )
        finalized = True
    finally:
        if not finalized:
            row = get_batch(db_path, batch_id=batch_id)
            if row is not None and str(row.get("status", "")).lower() == "running":
                finalize_batch(
                    db_path,
                    batch_id=batch_id,
                    status="failed",
                    completed_count=int(row.get("completed_count") or 0),
                    failed_count=max(1, int(row.get("failed_count") or 0)),
                    last_error="Worker terminato inaspettatamente (vedi output/logs/batch-*.log)",
                )


def _run_selected_ai_batch_body(
    *,
    batch_id: int,
    queue_file: Path,
    settings,
    db_path,
) -> None:
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    platform = Platform(str(data["platform"]))
    media_format = MediaFormat(str(data["media_format"]))
    category = str(data.get("category") or "").strip()
    marketing_objectives = list(data.get("marketing_objectives") or [])
    legacy_objective = data.get("marketing_objective")
    if legacy_objective and not marketing_objectives:
        marketing_objectives = [str(legacy_objective)]
    channels_raw = data.get("channels") or []
    channels = None
    if channels_raw:
        channels = [Platform(str(c)) for c in channels_raw]
    assets_raw = data.get("assets") or []
    assets = [
        DriveAsset(
            file_id=str(a["file_id"]),
            name=str(a.get("name") or a["file_id"]),
            mime_type=str(a.get("mime_type") or "image/jpeg"),
            category=a.get("category"),
            path_segments=list(a.get("path_segments") or []),
        )
        for a in assets_raw
    ]
    business_category = str(data.get("business_category") or category).strip().lower()
    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=False,
        oauth_browser=oauth_browser,
    )

    completed_count = 0
    failed_count = 0
    final_status = "completed"
    last_error: str | None = None

    for idx, asset in enumerate(assets):
        item_idx = idx + 1
        stop_msg = get_batch_stop_message(db_path, batch_id=batch_id)
        if stop_msg:
            add_batch_item(
                db_path,
                batch_id=batch_id,
                item_index=item_idx,
                status="cancelled",
                business_category=business_category,
                error_message=stop_msg,
                payload={"manual_stop": True},
                media_format=media_format,
            )
            last_error = stop_msg
            final_status = "cancelled"
            break
        try:
            biz = business_category or normalize_business_category(
                str(asset.category or category),
                {},
            )
            out = process_drive_asset(
                asset,
                platform=platform,
                media_format=media_format,
                settings=settings,
                business_category=biz,
                drive=drive,
                auto_approve=False,
                generate_copy=False,
                marketing_objectives=marketing_objectives,
                channels=channels,
            )
        except Exception as exc:
            msg = str(exc).strip() or repr(exc)
            failed_count += 1
            last_error = msg
            add_batch_item(
                db_path,
                batch_id=batch_id,
                item_index=item_idx,
                status="failed",
                source_asset_id=asset.file_id,
                source_asset_name=asset.name,
                business_category=business_category,
                error_message=msg,
                payload={"platform": platform.value, "media_format": media_format.value},
                media_format=media_format,
            )
            update_batch_progress(
                db_path,
                batch_id=batch_id,
                completed_count=completed_count,
                failed_count=failed_count,
                last_error=last_error,
                status="running",
            )
            final_status = "failed"
            break

        completed_count += 1
        revised = revised_prompt_from_process_output(out)
        if revised:
            append_batch_revised_prompt_log(
                settings.output_dir,
                batch_id,
                item_index=item_idx,
                image_id=int(out["image_id"]),
                source_asset_id=asset.file_id,
                source_asset_name=asset.name,
                method=str(
                    (out.get("visual_review") or {}).get("method")
                    or out.get("visual_method")
                    or ""
                ),
                revised_prompt=revised,
            )
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=item_idx,
            status="completed",
            source_asset_id=asset.file_id,
            source_asset_name=asset.name,
            business_category=business_category,
            image_id=int(out["image_id"]),
            rendered_file=str(out["processed_file"]),
            payload={
                "platform": platform.value,
                "media_format": media_format.value,
                "processed_file": str(out["processed_file"]),
            },
            media_format=media_format,
        )
        update_batch_progress(
            db_path,
            batch_id=batch_id,
            completed_count=completed_count,
            failed_count=failed_count,
            status="running",
        )

    if final_status == "completed" and completed_count < len(assets):
        final_status = "partial"

    finalize_batch(
        db_path,
        batch_id=batch_id,
        status=final_status,
        completed_count=completed_count,
        failed_count=failed_count,
        last_error=last_error,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Story AI batch on selected Drive assets.")
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--queue-file", type=str, required=True)
    args = parser.parse_args()
    run_selected_ai_batch(batch_id=int(args.batch_id), queue_file=Path(args.queue_file))


if __name__ == "__main__":
    main()
