"""Valutazione e dispatch delle regole di pubblicazione story (one-shot e settimanali)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from social_automation.db.store import (
    add_planning_event,
    delete_story_occurrence_slot,
    get_images_by_ids,
    list_story_schedule_rules,
    reserve_story_occurrence_slot,
    set_story_schedule_rule_active,
    story_occurrence_exists,
)
from social_automation.meta.client import MetaClient
from social_automation.models import Platform, infer_media_format_from_render_path
from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.settings import Settings, load_settings, resolve_media_file_path

_STORY_ONCE = "__once__"


def _caption_from_rule_detail(detail: str | None) -> str:
    raw = (detail or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return str(payload.get("caption", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw


def _parse_once_to_utc(scheduled_for: str) -> datetime:
    text = scheduled_for.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def collect_due_story_rules(
    db_path: Path,
    *,
    now: datetime,
    platform: Platform | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Elenco regole story da pubblicare ora (senza prenotare slot)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now_utc = now.astimezone(UTC)
    lim = max(1, int(limit))
    rows = list_story_schedule_rules(db_path, active_only=True, limit=2000)
    due: list[tuple[datetime, dict[str, Any]]] = []
    for r in rows:
        plat = Platform(str(r["platform"]))
        if platform is not None and plat != platform:
            continue
        mode = str(r["schedule_mode"] or "").strip().lower()
        rid = int(r["id"])
        if mode == "once":
            sf = str(r.get("scheduled_for") or "").strip()
            if not sf:
                continue
            try:
                fire_utc = _parse_once_to_utc(sf)
            except ValueError:
                continue
            if now_utc < fire_utc:
                continue
            if story_occurrence_exists(db_path, rule_id=rid, occurrence_date=_STORY_ONCE):
                continue
            due.append(
                (
                    fire_utc,
                    {
                        "rule_id": rid,
                        "image_id": int(r["image_id"]),
                        "platform": plat,
                        "image_path": str(r["image_path"]),
                        "caption": _caption_from_rule_detail(str(r.get("detail") or "")),
                        "schedule_mode": mode,
                        "occurrence_key": _STORY_ONCE,
                        "slot_label": sf,
                        "scheduled_for": fire_utc,
                    },
                )
            )
        elif mode == "weekly":
            tz_name = str(r.get("timezone") or "Europe/Rome").strip() or "Europe/Rome"
            try:
                z = ZoneInfo(tz_name)
            except Exception:
                continue
            wd_raw = r.get("weekday")
            tl = str(r.get("time_local") or "").strip()
            if wd_raw is None or not tl:
                continue
            try:
                target_wd = int(wd_raw)
            except (TypeError, ValueError):
                continue
            if target_wd < 0 or target_wd > 6:
                continue
            parts = tl.split(":")
            if len(parts) != 2:
                continue
            try:
                hh, mm = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                continue
            local_now = now_utc.astimezone(z)
            if local_now.weekday() != target_wd:
                continue
            slot_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if local_now < slot_local:
                continue
            dkey = local_now.date().isoformat()
            if story_occurrence_exists(db_path, rule_id=rid, occurrence_date=dkey):
                continue
            slot_utc = slot_local.astimezone(UTC)
            due.append(
                (
                    slot_utc,
                    {
                        "rule_id": rid,
                        "image_id": int(r["image_id"]),
                        "platform": plat,
                        "image_path": str(r["image_path"]),
                        "caption": _caption_from_rule_detail(str(r.get("detail") or "")),
                        "schedule_mode": mode,
                        "occurrence_key": dkey,
                        "slot_label": f"{dkey} {tl} {tz_name}",
                        "scheduled_for": slot_utc,
                    },
                )
            )
    due.sort(key=lambda x: x[0])
    return [pair[1] for pair in due[:lim]]


def run_story_rules_dispatch(
    db_path: Path,
    meta: MetaClient,
    *,
    now: datetime | None = None,
    platform: Platform | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> tuple[int, int, int]:
    """Prenota slot, pubblica, aggiorna regole. Ritorna (published, failed, skipped_reserve)."""
    s = settings if settings is not None else load_settings()
    n_now = now or datetime.now(UTC)
    candidates = collect_due_story_rules(db_path, now=n_now, platform=platform, limit=limit)
    published = 0
    failed = 0
    skipped_reserve = 0
    for c in candidates:
        rid = int(c["rule_id"])
        occ_key = str(c["occurrence_key"])
        plat = c["platform"]
        if not isinstance(plat, Platform):
            plat = Platform(str(plat))
        scheduled_for = c["scheduled_for"]
        if not isinstance(scheduled_for, datetime):
            raise TypeError("scheduled_for deve essere datetime")
        if not reserve_story_occurrence_slot(db_path, rule_id=rid, occurrence_date=occ_key):
            skipped_reserve += 1
            continue
        image_id = int(c["image_id"])
        img_rows = get_images_by_ids(db_path, [image_id])
        if img_rows:
            ok, reason = check_image_dispatch_gates(img_rows[0], s)
            if not ok:
                delete_story_occurrence_slot(db_path, rule_id=rid, occurrence_date=occ_key)
                add_planning_event(
                    db_path,
                    image_id=image_id,
                    platform=plat,
                    event_type="skipped",
                    scheduled_for=scheduled_for,
                    detail=f"dispatch-story-skipped: {reason}",
                )
                skipped_reserve += 1
                continue
        raw_path = str(c["image_path"])
        resolved = resolve_media_file_path(raw_path)
        image_path = resolved if resolved is not None else Path(raw_path)
        caption = str(c.get("caption") or "")
        sched_mode = str(c.get("schedule_mode") or "")
        detail_json = json.dumps(
            {
                "caption": caption,
                "story_rule_id": rid,
                "occurrence": occ_key,
                "slot": str(c.get("slot_label") or ""),
            },
            ensure_ascii=True,
        )
        add_planning_event(
            db_path,
            image_id=int(c["image_id"]),
            platform=plat,
            event_type="dispatched",
            scheduled_for=scheduled_for,
            detail="dispatch-story-rule",
        )
        try:
            if not image_path.is_file():
                raise FileNotFoundError(f"File render non trovato: {image_path}")
            mf = infer_media_format_from_render_path(image_path).value
            external_id = meta.publish_image(plat, image_path, caption, media_format=mf)
            add_planning_event(
                db_path,
                image_id=int(c["image_id"]),
                platform=plat,
                event_type="published",
                scheduled_for=scheduled_for,
                external_id=str(external_id),
                detail=detail_json,
            )
            if sched_mode == "once":
                set_story_schedule_rule_active(db_path, rule_id=rid, active=False)
            published += 1
        except Exception as e:
            failed += 1
            delete_story_occurrence_slot(db_path, rule_id=rid, occurrence_date=occ_key)
            add_planning_event(
                db_path,
                image_id=int(c["image_id"]),
                platform=plat,
                event_type="failed",
                scheduled_for=scheduled_for,
                detail=f"dispatch-story-rule: {e}",
            )
    return published, failed, skipped_reserve
