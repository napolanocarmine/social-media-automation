"""UI modifica / annullamento pianificazioni già a calendario."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

import streamlit as st

from social_automation.app_timezone import combine_app, format_hhmm_local, now_app, parse_iso_datetime
from social_automation.brand.copy_pack import (
    caption_for_platform,
    caption_from_planning_detail,
    planning_detail_with_caption,
)
from social_automation.db.store import (
    add_planning_event,
    get_copy_pack,
    latest_plan_for_image,
    list_pending_events,
    update_planning_event_external_id,
)
from social_automation.meta.client import MetaClient
from social_automation.models import MediaFormat, Platform, infer_media_format_from_render_path
from social_automation.settings import load_settings, resolve_media_file_path


def _event_label(ev: dict[str, Any], settings: Any) -> str:
    raw = str(ev.get("scheduled_for", ""))
    dt = parse_iso_datetime(raw, settings)
    when = dt.strftime("%d/%m/%Y %H:%M") if dt else format_hhmm_local(raw, settings)
    plat = str(ev.get("platform", "")).upper()
    name = str(ev.get("image_name", "")).strip() or f"immagine {ev.get('image_id')}"
    return f"#{ev.get('image_id')} · {plat} · {when} · {name}"


def _event_key(ev: dict[str, Any]) -> str:
    return f"{ev.get('image_id')}:{ev.get('platform')}"


def _default_date_time(ev: dict[str, Any], settings: Any) -> tuple[date, time]:
    dt = parse_iso_datetime(str(ev.get("scheduled_for", "")), settings)
    if dt is None:
        now = now_app(settings)
        return now.date(), now.time().replace(second=0, microsecond=0)
    return dt.date(), dt.time().replace(second=0, microsecond=0)


def _apply_meta_facebook_reschedule(
    *,
    settings: Any,
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


def _save_reschedule(
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


def _save_cancel(db_path: Path, *, ev: dict[str, Any]) -> str:
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


def _render_edit_form(
    db_path: Path,
    *,
    ev: dict[str, Any],
    settings: Any,
    form_key: str,
) -> None:
    image_id = int(ev["image_id"])
    platform = Platform(str(ev["platform"]))
    image_path = Path(str(ev.get("image_path", "")))
    media_format = infer_media_format_from_render_path(image_path)
    plan_date, plan_time = _default_date_time(ev, settings)

    pack = get_copy_pack(db_path, image_id=image_id)
    default_cap = caption_from_planning_detail(str(ev.get("detail", "")))
    if not default_cap:
        default_cap = caption_for_platform(pack, platform=platform, media_format=media_format)

    if image_path.is_file():
        st.image(str(image_path), caption=f"#{image_id} · {platform.value}", width=280)

    col_d, col_t = st.columns(2)
    with col_d:
        new_date = st.date_input("Nuova data", value=plan_date, key=f"{form_key}-date")
    with col_t:
        new_time = st.time_input("Nuova ora", value=plan_time, key=f"{form_key}-time")

    caption = ""
    if media_format == MediaFormat.POST:
        caption = st.text_area(
            "Caption per Meta",
            value=default_cap,
            height=100,
            key=f"{form_key}-caption",
        )
    else:
        st.caption("Story: si modifica solo data e ora (nessuna caption).")

    ext_id = (str(ev.get("external_id") or "")).strip()
    if ext_id:
        st.caption(f"ID Meta collegato: `{ext_id}`")

    col_save, col_cancel = st.columns(2)
    if col_save.button("Salva modifiche", type="primary", key=f"{form_key}-save"):
        try:
            msg = _save_reschedule(
                db_path,
                ev=ev,
                plan_date=new_date,
                plan_time=new_time,
                caption=caption,
                media_format=media_format,
            )
            st.session_state["calendar_edit_flash"] = {"level": "success", "body": msg}
            st.session_state.pop("calendar-edit-key", None)
        except Exception as exc:
            st.session_state["calendar_edit_flash"] = {
                "level": "error",
                "body": f"Modifica fallita: {exc}",
            }
        st.rerun()

    if col_cancel.button("Annulla pianificazione", key=f"{form_key}-drop"):
        try:
            msg = _save_cancel(db_path, ev=ev)
            st.session_state["calendar_edit_flash"] = {"level": "warning", "body": msg}
            st.session_state.pop("calendar-edit-key", None)
        except Exception as exc:
            st.session_state["calendar_edit_flash"] = {
                "level": "error",
                "body": f"Annullamento fallito: {exc}",
            }
        st.rerun()


def render_calendar_edit_section(
    db_path: Path,
    *,
    settings: Any,
    month_items: list[dict[str, Any]],
    platform_filter: Platform | None = None,
) -> None:
    """Form per modificare o annullare pianificazioni (tab Calendario)."""
    flash = st.session_state.pop("calendar_edit_flash", None)
    if flash:
        lvl = str(flash.get("level", "success"))
        body = str(flash.get("body", ""))
        if lvl == "error":
            st.error(body)
        elif lvl == "warning":
            st.warning(body)
        else:
            st.success(body)

    st.subheader("Modifica pianificazioni")
    st.caption(
        "Sposta data/ora o aggiorna la caption di post e story già in calendario. "
        "Per Facebook post con token Meta configurato, la programmazione nativa viene aggiornata."
    )

    pool = list(month_items)
    show_all = st.checkbox("Mostra tutte le pianificazioni attive (non solo questo mese)", value=False)
    if show_all:
        pool = list_pending_events(db_path, platform=platform_filter, limit=500)

    if not pool:
        st.info("Nessuna pianificazione da modificare.")
        return

    pool = sorted(pool, key=lambda r: str(r.get("scheduled_for", "")))
    labels = [_event_label(ev, settings) for ev in pool]
    selected_idx = st.selectbox(
        "Seleziona evento",
        options=list(range(len(pool))),
        format_func=lambda i: labels[int(i)],
        key="calendar-edit-select",
    )
    ev = pool[int(selected_idx)]
    st.session_state["calendar-edit-key"] = _event_key(ev)
    _render_edit_form(
        db_path,
        ev=ev,
        settings=settings,
        form_key=f"cal-edit-{_event_key(ev)}",
    )
