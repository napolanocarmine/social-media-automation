"""Logica pianificazione post/story e copy."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from social_automation.app_timezone import app_timezone_name, combine_app
from social_automation.brand.copy_pack import caption_for_platform, planning_detail_with_caption
from social_automation.brand.prompt_context import (
    normalize_channels,
    normalize_marketing_objectives,
)
from social_automation.config_loaders import load_schedule_yaml, resolve_schedule_path
from social_automation.db.store import (
    add_planning_event,
    add_story_schedule_rule,
    count_plannable_images,
    get_copy_pack,
    get_image_record,
    get_images_by_ids,
    latest_plan_for_image,
    list_plannable_images,
    update_planning_event_external_id,
)
from social_automation.meta.client import MetaClient
from social_automation.models import MediaFormat, Platform
from social_automation.scheduling.slot_planner import suggest_next_free_slot
from social_automation.services.images import _serialize_image_row
from social_automation.settings import Settings, load_settings, resolve_media_file_path
from social_automation.workflow.process_photo import generate_copy_for_image

PLANNABLE_PAGE_SIZE_DEFAULT = 10
WEEKDAY_IT = [
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
]


def list_plannable(
    db_path: Path,
    *,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str | None,
    page: int = 0,
    page_size: int = PLANNABLE_PAGE_SIZE_DEFAULT,
    settings: Settings | None = None,
) -> dict[str, Any]:
    total = count_plannable_images(
        db_path,
        platform=platform,
        business_category=business_category,
        media_format=media_format,
        require_quality_pass=False,
        require_manual_publication_valid=True,
    )
    page_size = max(1, min(100, int(page_size)))
    page = max(0, int(page))
    rows = list_plannable_images(
        db_path,
        platform=platform,
        business_category=business_category,
        media_format=media_format,
        require_quality_pass=False,
        require_manual_publication_valid=True,
        limit=page_size,
        offset=page * page_size,
    )
    return {
        "items": [_serialize_image_row(r, db_path=db_path, settings=settings) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total else 0,
    }


def get_copy_pack_for_image(db_path: Path, *, image_id: int) -> dict[str, Any] | None:
    return get_copy_pack(db_path, image_id=image_id)


def generate_image_copy(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    media_format: MediaFormat,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[str] | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or load_settings()
    channel_platforms = normalize_channels(
        channels or [platform.value],
        fallback_platform=platform,
    )
    objectives = normalize_marketing_objectives(
        marketing_objectives,
        legacy_single=marketing_objective,
    )
    return generate_copy_for_image(
        image_id,
        platform=platform,
        media_format=media_format,
        marketing_objectives=objectives,
        channels=channel_platforms,
        settings=s,
    )


def suggest_editorial_slot(
    db_path: Path,
    *,
    platform: Platform,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    s = settings or load_settings()
    sched_path = resolve_schedule_path(s.schedule_config_path)
    if not sched_path.is_file():
        raise FileNotFoundError(
            "Calendario editoriale non trovato. Copia config/schedule.example.yaml "
            "in config/schedule.yaml."
        )
    schedule = load_schedule_yaml(sched_path)
    suggested = suggest_next_free_slot(db_path, schedule, platform=platform)
    if suggested is None:
        return None
    tz = ZoneInfo(schedule.timezone)
    local_dt = suggested.scheduled_for.astimezone(tz)
    return {
        "platform": suggested.platform.value,
        "scheduled_for": suggested.scheduled_for.isoformat(),
        "scheduled_date": local_dt.date().isoformat(),
        "scheduled_time": local_dt.strftime("%H:%M"),
        "weekday": suggested.weekday,
        "weekday_label": WEEKDAY_IT[local_dt.weekday()],
        "time_hhmm": suggested.time_hhmm,
        "timezone": schedule.timezone,
    }


def save_plan(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    media_format: MediaFormat,
    plan_date: date | None = None,
    plan_time: time | None = None,
    caption: str | None = None,
    story_schedule_mode: str | None = None,
    story_weekday: int | None = None,
    story_time_local: str | None = None,
    story_timezone: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or load_settings()
    rows = get_images_by_ids(db_path, [image_id])
    if not rows:
        raise ValueError(f"Immagine #{image_id} non trovata")
    row = rows[0]
    image_name = str(row.get("name", "")).strip() or f"Immagine {image_id}"

    if media_format == MediaFormat.STORY and story_schedule_mode == "weekly":
        tz_clean = (story_timezone or "").strip() or app_timezone_name(s)
        ZoneInfo(tz_clean)
        tl = story_time_local or "10:00"
        add_story_schedule_rule(
            db_path,
            image_id=image_id,
            platform=platform,
            schedule_mode="weekly",
            timezone_name=tz_clean,
            weekday=int(story_weekday or 0),
            time_local=tl,
            detail=None,
        )
        return {
            "message": (
                "Regola story ricorrente creata. Esegui dispatch-scheduled all'orario indicato."
            ),
            "image_id": image_id,
            "platform": platform.value,
        }

    if plan_date is None or plan_time is None:
        raise ValueError("Data e ora obbligatorie per la pianificazione")

    scheduled_for = combine_app(plan_date, plan_time, s)
    pack = get_copy_pack(db_path, image_id=image_id)
    cap_from_pack = caption_for_platform(pack, platform=platform, media_format=media_format)
    if media_format == MediaFormat.POST and not (caption or "").strip() and not cap_from_pack:
        raise ValueError("Genera il copy prima di pianificare un post.")

    latest = latest_plan_for_image(db_path, image_id=image_id, platform=platform)
    event_type = "planned"
    if latest is not None and str(latest.get("event_type", "")).lower() in {
        "planned",
        "rescheduled",
    }:
        event_type = "rescheduled"
    prev_ext = ""
    if latest is not None and str(latest.get("event_type", "")).lower() in {
        "planned",
        "rescheduled",
    }:
        prev_ext = (str(latest.get("external_id") or "")).strip()

    story_detail = None
    if media_format != MediaFormat.STORY:
        cap_text = (caption or "").strip() or cap_from_pack
        story_detail = planning_detail_with_caption(cap_text) or (cap_text or None)

    event_id = add_planning_event(
        db_path,
        image_id=image_id,
        platform=platform,
        event_type=event_type,
        scheduled_for=scheduled_for,
        detail=story_detail,
    )

    cap_publish = (
        ""
        if media_format == MediaFormat.STORY
        else ((caption or "").strip() or cap_from_pack or image_name)
    )
    meta_fb_ok = False
    ig_note = False
    if s.meta_page_access_token.strip():
        meta_client = MetaClient(
            s.meta_page_access_token.strip(),
            s.meta_ig_user_id.strip(),
            graph_version=(s.meta_graph_version or "v22.0").strip(),
            settings=s,
        )
        resolved = resolve_media_file_path(str(row.get("path", "")))
        image_file = resolved if resolved is not None else Path(str(row.get("path", "")))
        if (
            platform == Platform.FACEBOOK
            and media_format == MediaFormat.POST
            and image_file.is_file()
        ):
            if prev_ext:
                meta_client.delete_graph_object(prev_ext)
            ext_id = meta_client.schedule_facebook_photo(
                image_file,
                cap_publish,
                publish_at=scheduled_for,
            )
            update_planning_event_external_id(db_path, event_id=event_id, external_id=ext_id)
            meta_fb_ok = True
        elif platform == Platform.INSTAGRAM and media_format == MediaFormat.POST:
            ig_note = True

    lines = [f"Pianificazione salvata per #{image_id}."]
    if meta_fb_ok:
        lines.append("Programmazione nativa su Meta (Facebook Page) creata.")
    if media_format == MediaFormat.STORY:
        lines.append(
            "Story: orario salvato nel database. Usa dispatch-scheduled all'orario per pubblicare."
        )
    elif platform == Platform.INSTAGRAM and ig_note and media_format == MediaFormat.POST:
        lines.append(
            "Instagram: data salvata nel database. Usa dispatch-scheduled all'orario pianificato."
        )

    return {
        "message": "\n".join(lines),
        "event_id": event_id,
        "image_id": image_id,
        "platform": platform.value,
        "scheduled_for": scheduled_for.isoformat(),
    }


def reschedule_plan(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    plan_date: date,
    plan_time: time,
    caption: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    from social_automation.models import infer_media_format_from_render_path

    s = settings or load_settings()
    row = get_image_record(db_path, image_id=image_id)
    if row is None:
        raise ValueError(f"Immagine #{image_id} non trovata")
    image_path = Path(str(row.get("path", "")))
    media_format = infer_media_format_from_render_path(image_path)
    scheduled_for = combine_app(plan_date, plan_time, s)

    latest = latest_plan_for_image(db_path, image_id=image_id, platform=platform)
    prev_ext = ""
    if latest is not None and str(latest.get("event_type", "")).lower() in {
        "planned",
        "rescheduled",
    }:
        prev_ext = (str(latest.get("external_id") or "")).strip()

    detail = None
    if media_format != MediaFormat.STORY:
        cap_text = (caption or "").strip()
        if not cap_text:
            pack = get_copy_pack(db_path, image_id=image_id)
            cap_text = caption_for_platform(pack, platform=platform, media_format=media_format)
        if media_format == MediaFormat.POST and not cap_text:
            raise ValueError("La caption è obbligatoria per un post.")
        detail = planning_detail_with_caption(cap_text) or (cap_text or None)

    event_id = add_planning_event(
        db_path,
        image_id=image_id,
        platform=platform,
        event_type="rescheduled",
        scheduled_for=scheduled_for,
        detail=detail,
    )

    meta_note = ""
    if (
        platform == Platform.FACEBOOK
        and media_format == MediaFormat.POST
        and s.meta_page_access_token.strip()
    ):
        resolved = resolve_media_file_path(str(row.get("path", "")))
        image_file = resolved if resolved is not None else image_path
        cap_publish = (caption or "").strip()
        if not cap_publish:
            pack = get_copy_pack(db_path, image_id=image_id)
            cap_publish = caption_for_platform(pack, platform=platform, media_format=media_format)
        cap_publish = cap_publish or str(row.get("name", "")).strip() or f"Immagine {image_id}"
        meta_client = MetaClient(
            s.meta_page_access_token.strip(),
            s.meta_ig_user_id.strip(),
            graph_version=(s.meta_graph_version or "v22.0").strip(),
            settings=s,
        )
        if not image_file.is_file():
            raise ValueError("File immagine assente sul disco.")
        if prev_ext:
            meta_client.delete_graph_object(prev_ext)
        ext_id = meta_client.schedule_facebook_photo(
            image_file,
            cap_publish,
            publish_at=scheduled_for,
        )
        update_planning_event_external_id(db_path, event_id=event_id, external_id=ext_id)
        meta_note = " Programmazione Meta (Facebook) aggiornata."

    when = scheduled_for.strftime("%d/%m/%Y %H:%M")
    return {
        "message": f"Pianificazione aggiornata al {when}.{meta_note}",
        "event_id": event_id,
        "image_id": image_id,
        "platform": platform.value,
        "scheduled_for": scheduled_for.isoformat(),
    }


def cancel_plan(
    db_path: Path,
    *,
    image_id: int,
    platform: Platform,
    settings: Settings | None = None,
) -> dict[str, Any]:
    from social_automation.app_timezone import parse_iso_datetime

    s = settings or load_settings()
    latest = latest_plan_for_image(db_path, image_id=image_id, platform=platform)
    prev_ext = ""
    scheduled_for = None
    if latest is not None:
        prev_ext = (str(latest.get("external_id") or "")).strip()
        raw = str(latest.get("scheduled_for", "")).strip()
        scheduled_for = parse_iso_datetime(raw, s)

    if prev_ext and s.meta_page_access_token.strip():
        meta_client = MetaClient(
            s.meta_page_access_token.strip(),
            s.meta_ig_user_id.strip(),
            graph_version=(s.meta_graph_version or "v22.0").strip(),
            settings=s,
        )
        meta_client.delete_graph_object(prev_ext)

    add_planning_event(
        db_path,
        image_id=image_id,
        platform=platform,
        event_type="cancelled",
        scheduled_for=scheduled_for,
        detail="annullato da calendario",
    )
    meta_note = " Programmazione Meta rimossa." if prev_ext else ""
    return {
        "message": f"Pianificazione annullata.{meta_note}",
        "image_id": image_id,
        "platform": platform.value,
    }
