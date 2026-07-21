"""UI modifica / annullamento pianificazioni già a calendario."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

import streamlit as st

from social_automation.app_timezone import format_hhmm_local, now_app, parse_iso_datetime
from social_automation.brand.copy_pack import (
    caption_for_platform,
    caption_from_planning_detail,
)
from social_automation.db.store import get_copy_pack, list_pending_events
from social_automation.models import MediaFormat, Platform, infer_media_format_from_render_path
from social_automation.services.calendar_edit import save_cancel, save_reschedule


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
            msg = save_reschedule(
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
            msg = save_cancel(db_path, ev=ev)
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
