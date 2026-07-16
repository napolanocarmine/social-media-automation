"""Workflow «Prepara settimana»: processa foto, approvazione Story AI, pianificazione slot."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from social_automation.app_timezone import now_app
from social_automation.brand.copy_pack import caption_for_platform, copy_approved, planning_detail_with_caption
from social_automation.config_loaders import load_schedule_yaml
from social_automation.db.store import (
    add_planning_event,
    get_copy_pack,
    get_images_by_ids,
    latest_metadata_for_image,
    list_plannable_image_ids,
    set_image_manual_publication_valid,
)
from social_automation.image_quality_onnx import quality_gate_configured
from social_automation.models import MediaFormat, Platform
from social_automation.processing.image_adjust import approved_from_retouch
from social_automation.scheduling.slot_planner import list_free_schedule_slots
from social_automation.settings import Settings, load_settings
from social_automation.workflow.process_photo import process_drive_story_photo

_LOG = logging.getLogger(__name__)


@dataclass
class PrepareWeekResult:
    planned: int = 0
    processed: int = 0
    rendered: int = 0  # alias retrocompatibilità CLI
    skipped_occupied: int = 0
    skipped_quality: int = 0
    skipped_borderline: int = 0
    skipped_no_asset: int = 0
    auto_approved: int = 0
    vision_evaluated: int = 0
    errors: list[str] = field(default_factory=list)
    assignments: list[dict[str, Any]] = field(default_factory=list)


def _p_good_from_row(image_row: dict[str, Any]) -> float | None:
    cls = str(image_row.get("quality_predicted_class") or "").strip().lower()
    conf = image_row.get("quality_predicted_confidence")
    if conf is None:
        return None
    c = float(conf)
    if cls == "good":
        return c
    if cls == "bad":
        return 1.0 - c
    return None


def _quality_tier(
    image_row: dict[str, Any],
    settings: Settings,
) -> str:
    """``good`` | ``borderline`` | ``bad`` | ``unknown``."""
    if not quality_gate_configured(settings):
        return "unknown"
    q = image_row.get("is_valid_by_quality_evaluation")
    if q is not None and int(q) == 1:
        return "good"
    p_good = _p_good_from_row(image_row)
    if p_good is None:
        return "unknown" if q is None else "bad"
    thr = float(settings.image_quality_confidence_threshold)
    margin = float(settings.image_quality_borderline_margin)
    if p_good >= thr:
        return "good"
    if p_good >= thr - margin:
        return "borderline"
    return "bad"


def _story_ai_approved(row: dict[str, Any]) -> bool | None:
    """True/False se copy/retouch JSON presenti, None se assenti."""
    import json

    copy_raw = row.get("copy_json")
    retouch_raw = row.get("retouch_json")
    copy_data = None
    retouch_data = None
    if copy_raw:
        try:
            copy_data = json.loads(str(copy_raw))
        except ValueError:
            copy_data = None
    if retouch_raw:
        try:
            retouch_data = json.loads(str(retouch_raw))
        except ValueError:
            retouch_data = None
    if copy_data is None and retouch_data is None:
        return None
    visual_ok = approved_from_retouch(retouch_data or {}) if retouch_data else True
    copy_ok = copy_approved(copy_data)
    if not visual_ok or not copy_ok:
        return False
    return True


def _pick_plannable_image_id(
    db_path: Path,
    *,
    platform: Platform,
    category: str | None,
    require_quality: bool,
) -> int | None:
    ids = list_plannable_image_ids(
        db_path,
        platform=platform,
        business_category=category,
        media_format=MediaFormat.POST,
        require_quality_pass=require_quality,
        require_manual_publication_valid=False,
    )
    return ids[0] if ids else None


def _auto_approve_if_eligible(
    db_path: Path,
    image_id: int,
    image_row: dict[str, Any],
    *,
    settings: Settings,
) -> bool:
    tier = _quality_tier(image_row, settings)
    if tier == "bad":
        return False
    if tier == "borderline":
        return False
    story_ok = _story_ai_approved(image_row)
    if story_ok is False:
        return False
    if story_ok is True:
        set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
        return True
    if int(image_row.get("vision_eval_pass") or 0) == 1:
        set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
        return True
    return False


def prepare_week(
    *,
    schedule_path: Path | None = None,
    settings: Settings | None = None,
    start: datetime | None = None,
    days: int = 7,
    dry_run: bool = False,
    try_render: bool = True,
    try_process: bool | None = None,
) -> PrepareWeekResult:
    """
    Per ogni slot libero nel periodo:
    - trova o processa un'immagine per la categoria dello slot;
    - auto-approva se Story AI (o vision legacy) OK;
    - pianifica nel calendario (salvo ``dry_run``).
    """
    s = settings or load_settings()
    do_process = try_process if try_process is not None else try_render
    sched_path = schedule_path or s.schedule_config_path
    if not sched_path.is_file():
        raise FileNotFoundError(f"Schedule non trovato: {sched_path}")
    schedule = load_schedule_yaml(sched_path)
    base = start or now_app(s)
    if base.tzinfo is None:
        base = base.replace(tzinfo=now_app(s).tzinfo)
    end = base + timedelta(days=max(1, int(days)))
    free_slots = list_free_schedule_slots(s.db_path, schedule, start=base, end=end)
    result = PrepareWeekResult()

    for slot in free_slots:
        category = slot.category
        image_id = _pick_plannable_image_id(
            s.db_path,
            platform=slot.platform,
            category=category,
            require_quality=bool(s.dispatch_require_quality_pass),
        )

        if image_id is None and do_process and not dry_run:
            if not category:
                result.skipped_no_asset += 1
                result.errors.append(
                    f"Slot {slot.platform.value} {slot.scheduled_for}: categoria mancante nello schedule"
                )
                continue
            try:
                out = process_drive_story_photo(
                    category=category,
                    platform=slot.platform,
                    media_format=MediaFormat.POST,
                    settings=s,
                )
                image_id = int(out["image_id"])
                result.processed += 1
                result.rendered += 1
            except Exception as exc:
                result.skipped_no_asset += 1
                result.errors.append(f"Process foto fallito {slot.platform.value} {category}: {exc}")
                continue
        elif image_id is None:
            result.skipped_no_asset += 1
            continue

        rows = get_images_by_ids(s.db_path, [image_id])
        if not rows:
            result.errors.append(f"image_id={image_id} non trovato")
            continue
        row = rows[0]
        tier = _quality_tier(row, s)
        if tier == "bad":
            result.skipped_quality += 1
            continue
        if tier == "borderline":
            result.skipped_borderline += 1
            continue

        meta = latest_metadata_for_image(s.db_path, image_id=image_id)
        biz_cat = str((meta or {}).get("business_category") or category or "").strip() or None

        approved = int(row.get("is_valid_for_publication") or 0) == 1
        if not approved:
            if dry_run:
                story_ok = _story_ai_approved(row)
                would_auto = story_ok is True or (
                    story_ok is None and int(row.get("vision_eval_pass") or 0) == 1
                )
                if tier == "borderline" or not would_auto:
                    result.skipped_borderline += 1
                    continue
            elif _auto_approve_if_eligible(s.db_path, image_id, row, settings=s):
                result.auto_approved += 1
                approved = True
            else:
                result.skipped_borderline += 1
                continue
        elif not dry_run and _auto_approve_if_eligible(
            s.db_path, image_id, row, settings=s
        ):
            result.auto_approved += 1

        copy_data = get_copy_pack(s.db_path, image_id=image_id)
        if not copy_data and row.get("copy_json"):
            import json

            try:
                copy_data = json.loads(str(row["copy_json"]))
            except ValueError:
                copy_data = None
        caption = caption_for_platform(
            copy_data,
            platform=slot.platform,
            media_format=MediaFormat.POST,
        )
        plan_detail = planning_detail_with_caption(caption) or f"prepare-week:{category or biz_cat or ''}"

        assignment = {
            "image_id": image_id,
            "platform": slot.platform.value,
            "scheduled_for": slot.scheduled_for.isoformat(),
            "category": category or biz_cat,
            "weekday": slot.weekday,
            "time": slot.time_hhmm,
            "caption": caption,
        }
        result.assignments.append(assignment)

        if dry_run:
            result.planned += 1
            continue

        add_planning_event(
            s.db_path,
            image_id=image_id,
            platform=slot.platform,
            event_type="planned",
            scheduled_for=slot.scheduled_for,
            detail=plan_detail,
        )
        result.planned += 1

    return result
