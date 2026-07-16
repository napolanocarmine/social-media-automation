from __future__ import annotations

import argparse

from social_automation.db.store import (
    add_batch_item,
    finalize_batch,
    get_batch_stop_message,
    update_batch_progress,
)
from social_automation.models import MediaFormat, Platform
from social_automation.settings import load_settings
from social_automation.services.process_photo import run_process_photo


def run_batch_job(
    *,
    batch_id: int,
    category: str,
    platform: Platform,
    total: int,
    target_year: int | None = None,
    target_month: int | None = None,
    media_format: MediaFormat = MediaFormat.POST,
) -> None:
    settings = load_settings()
    db_path = settings.db_path
    completed_count = 0
    failed_count = 0
    final_status = "completed"
    last_error: str | None = None

    for idx in range(max(0, int(total))):
        item_idx = idx + 1
        stop_msg = get_batch_stop_message(db_path, batch_id=batch_id)
        if stop_msg:
            add_batch_item(
                db_path,
                batch_id=batch_id,
                item_index=item_idx,
                status="cancelled",
                business_category=category,
                error_message=stop_msg,
                payload={
                    "platform": platform.value,
                    "media_format": media_format.value,
                    "manual_stop": True,
                },
                media_format=media_format,
            )
            last_error = stop_msg
            final_status = "cancelled"
            break
        try:
            result = run_process_photo(
                category=category,
                platform=platform,
                target_year=target_year,
                target_month=target_month,
                media_format=media_format,
                open_browser=False,
            )
        except Exception as e:
            msg = str(e).strip() or repr(e)
            if "Nessun asset trovato" in msg:
                add_batch_item(
                    db_path,
                    batch_id=batch_id,
                    item_index=item_idx,
                    status="skipped",
                    business_category=category,
                    error_message=msg,
                    payload={
                        "platform": platform.value,
                        "media_format": media_format.value,
                    },
                    media_format=media_format,
                )
                final_status = "partial" if completed_count > 0 else "failed"
                if completed_count == 0:
                    failed_count += 1
                    last_error = msg
                break

            failed_count += 1
            last_error = msg
            add_batch_item(
                db_path,
                batch_id=batch_id,
                item_index=item_idx,
                status="failed",
                business_category=category,
                error_message=msg,
                payload={
                    "platform": platform.value,
                    "media_format": media_format.value,
                },
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
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=item_idx,
            status="completed",
            source_asset_id=str(result.get("source_asset_id", "")).strip() or None,
            source_asset_name=str(result.get("source_asset_name", "")).strip() or None,
            business_category=str(result.get("business_category", "")).strip() or None,
            template_id=str(result.get("template_id", "")).strip() or None,
            image_id=int(result["db_image_id"]),
            rendered_file=str(result["rendered_file"]),
            payload={
                "platform": str(result.get("platform", "")).strip(),
                "media_format": str(
                    result.get("media_format", media_format.value)
                ).strip()
                or media_format.value,
                "selected_asset": str(result.get("selected_asset", "")).strip(),
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

    if final_status == "completed" and completed_count < total:
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
    parser = argparse.ArgumentParser(description="Run background batch Story AI photo job.")
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--category", type=str, required=True)
    parser.add_argument("--platform", type=str, required=True)
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--target-year", type=int, default=None)
    parser.add_argument("--target-month", type=int, default=None)
    parser.add_argument(
        "--media-format",
        type=str,
        default=MediaFormat.POST.value,
        choices=[MediaFormat.POST.value, MediaFormat.STORY.value],
        help="Formato del render: post (feed) o story (verticale 9:16)",
    )
    args = parser.parse_args()
    run_batch_job(
        batch_id=int(args.batch_id),
        category=str(args.category).strip(),
        platform=Platform(str(args.platform).strip()),
        total=max(0, int(args.total)),
        target_year=int(args.target_year) if args.target_year is not None else None,
        target_month=int(args.target_month) if args.target_month is not None else None,
        media_format=MediaFormat(str(args.media_format).strip().lower()),
    )


if __name__ == "__main__":
    main()
