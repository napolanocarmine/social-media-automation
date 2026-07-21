"""Modifica / annullamento pianificazioni (logica senza UI)."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

from social_automation.app_timezone import combine_app, parse_iso_datetime
from social_automation.brand.copy_pack import (
    caption_for_platform,
    planning_detail_with_caption,
)
from social_automation.db.store import (
    add_planning_event,
    get_copy_pack,
    latest_plan_for_image,
    update_planning_event_external_id,
)
from social_automation.meta.client import MetaClient
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings, load_settings, resolve_media_file_path


def _apply_meta_facebook_reschedule(
    *,
    settings: Settings,
    image_path: Path,
    caption: str,
    scheduled_for: Any,
    prev_ext: str,
    event_id: int,
    db_path: Path,
) -> None:
    if not settings.meta_page_access_token.strip():
        return
    meta_client = MetaClient(
        settings.meta_page_access_token.strip(),
        settings.meta_ig_user_id.strip(),
        graph_version=(settings.meta_graph_version or "v22.0").strip(),
        settings=settings,
    )
    if not image_path.is_file():
        raise ValueError("File immagine assente sul disco.")
    if prev_ext:
        meta_client.delete_graph_object(prev_ext)
    ext_id = meta_client.schedule_facebook_photo(
        image_path,
        caption,
        publish_at=scheduled_for,
    )
    update_planning_event_external_id(db_path, event_id=event_id, external_id=ext_id)


def save_reschedule(
    db_path: Path,
    *,
    ev: dict[str, Any],
    plan_date: date,
    plan_time: time,
    caption: str,
    media_format: MediaFormat,
) -> str:
    settings = load_settings()
    image_id = int(ev["image_id"])
    platform = Platform(str(ev["platform"]))
    scheduled_for = combine_app(plan_date, plan_time, settings)

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
        and settings.meta_page_access_token.strip()
    ):
        image_path_raw = str(ev.get("image_path", ""))
        resolved = resolve_media_file_path(image_path_raw)
        image_file = resolved if resolved is not None else Path(image_path_raw)
        cap_publish = (caption or "").strip()
        if not cap_publish:
            pack = get_copy_pack(db_path, image_id=image_id)
            cap_publish = caption_for_platform(pack, platform=platform, media_format=media_format)
        cap_publish = cap_publish or str(ev.get("image_name", "")).strip() or f"Immagine {image_id}"
        _apply_meta_facebook_reschedule(
            settings=settings,
            image_path=image_file,
            caption=cap_publish,
            scheduled_for=scheduled_for,
            prev_ext=prev_ext,
            event_id=event_id,
            db_path=db_path,
        )
        meta_note = " Programmazione Meta (Facebook) aggiornata."

    when = scheduled_for.strftime("%d/%m/%Y %H:%M")
    return f"Pianificazione aggiornata al {when}.{meta_note}"


def save_cancel(db_path: Path, *, ev: dict[str, Any]) -> str:
    settings = load_settings()
    image_id = int(ev["image_id"])
    platform = Platform(str(ev["platform"]))
    latest = latest_plan_for_image(db_path, image_id=image_id, platform=platform)
    prev_ext = ""
    scheduled_for = None
    if latest is not None:
        prev_ext = (str(latest.get("external_id") or "")).strip()
        raw = str(latest.get("scheduled_for", "")).strip()
        scheduled_for = parse_iso_datetime(raw, settings)

    if prev_ext and settings.meta_page_access_token.strip():
        meta_client = MetaClient(
            settings.meta_page_access_token.strip(),
            settings.meta_ig_user_id.strip(),
            graph_version=(settings.meta_graph_version or "v22.0").strip(),
            settings=settings,
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
    return f"Pianificazione annullata.{meta_note}"
