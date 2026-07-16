"""Calendario pianificazione."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from social_automation.app_timezone import (
    format_hhmm_local,
    month_bounds_local,
    parse_iso_datetime,
)
from social_automation.brand.copy_pack import caption_for_platform, caption_from_planning_detail
from social_automation.db.store import get_copy_pack, list_calendar_items, list_pending_events
from social_automation.models import Platform, infer_media_format_from_render_path
from social_automation.services.media import media_urls_for_image
from social_automation.settings import Settings


def serialize_calendar_event(ev: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    raw_when = str(ev.get("scheduled_for", ""))
    dt = parse_iso_datetime(raw_when, settings)
    image_path = Path(str(ev.get("image_path", "")))
    media_format = infer_media_format_from_render_path(image_path)
    image_id = int(ev["image_id"])
    pack = get_copy_pack(settings.db_path, image_id=image_id)
    platform = Platform(str(ev.get("platform")))
    default_cap = caption_from_planning_detail(str(ev.get("detail", "")))
    if not default_cap:
        default_cap = caption_for_platform(pack, platform=platform, media_format=media_format)
    day = dt.day if dt else None
    return {
        "id": int(ev["id"]),
        "image_id": image_id,
        "image_name": str(ev.get("image_name") or ""),
        "platform": str(ev.get("platform") or ""),
        "event_type": str(ev.get("event_type") or ""),
        "scheduled_for": raw_when,
        "time_label": format_hhmm_local(raw_when, settings),
        "day": day,
        "external_id": ev.get("external_id"),
        "detail": ev.get("detail"),
        "caption": default_cap,
        "media_format": media_format.value,
        "media": media_urls_for_image(image_id),
    }


def list_calendar(
    db_path: Path,
    *,
    year: int,
    month: int,
    platform: Platform | None = None,
    business_category: str | None = None,
    limit: int = 500,
    settings: Settings | None = None,
) -> dict[str, Any]:
    from social_automation.settings import load_settings

    s = settings or load_settings()
    start_dt, end_dt = month_bounds_local(year, month, s)
    items = list_calendar_items(
        db_path,
        start_inclusive=start_dt,
        end_exclusive=end_dt,
        platform=platform,
        business_category=business_category,
        limit=limit,
    )
    serialized = [serialize_calendar_event(ev, settings=s) for ev in items]
    by_day: dict[int, list[dict[str, Any]]] = {}
    for ev in serialized:
        if ev.get("day") is not None:
            by_day.setdefault(int(ev["day"]), []).append(ev)
    return {
        "year": year,
        "month": month,
        "total": len(serialized),
        "items": serialized,
        "by_day": by_day,
    }


def list_active_plans(
    db_path: Path,
    *,
    platform: Platform | None = None,
    all_active: bool = False,
    year: int | None = None,
    month: int | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    from social_automation.settings import load_settings

    s = settings or load_settings()
    if all_active:
        pool = list_pending_events(db_path, platform=platform, limit=500)
    else:
        if year is None or month is None:
            raise ValueError("year e month richiesti se all_active=false")
        start_dt, end_dt = month_bounds_local(year, month, s)
        pool = list_calendar_items(
            db_path,
            start_inclusive=start_dt,
            end_exclusive=end_dt,
            platform=platform,
            limit=500,
        )
    pool = sorted(pool, key=lambda r: str(r.get("scheduled_for", "")))
    return [serialize_calendar_event(ev, settings=s) for ev in pool]
