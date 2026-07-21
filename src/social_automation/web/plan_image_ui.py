"""UI Step Pianifica (selezione immagine, copy on demand, schedule)."""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from social_automation.app_timezone import (
    app_timezone_name,
    combine_app,
    now_app,
    today_app,
)
from social_automation.brand.copy_pack import caption_for_platform, planning_detail_with_caption
from social_automation.brand.prompt_context import (
    MARKETING_OBJECTIVES,
    normalize_channels,
    normalize_marketing_objective,
)
from social_automation.db.store import (
    add_planning_event,
    add_story_schedule_rule,
    get_copy_pack,
    get_images_by_ids,
    latest_plan_for_image,
    list_plannable_image_ids,
    list_plannable_images,
    update_planning_event_external_id,
)
from social_automation.meta.client import MetaClient
from social_automation.models import MediaFormat, Platform
from social_automation.scheduling.slot_planner import suggest_next_free_slot
from social_automation.settings import load_settings, resolve_media_file_path
from social_automation.workflow.process_photo import generate_copy_for_image

_PLAN_IMAGE_PAGE_SIZE = 10


def render_plan_image_page(
    settings_db_path: Path,
    *,
    business_category_options: list[str],
    media_format_label: Any,
    weekday_it: list[str],
    plan_preview_dialog: Any,
    render_copy_pack_preview: Any,
    render_workflow_footer: Any,
    load_schedule_yaml: Any,
    resolve_schedule_path: Any,
) -> None:
    st.caption(
        "Step 1: scegli **una** immagine approvata e genera il copy (solo post). "
        "Step 2: pianifica data e ora."
    )
    flash = st.session_state.pop("plan_save_flash", None)
    if flash:
        lvl = str(flash.get("level", "success"))
        body = str(flash.get("body", ""))
        if lvl == "error":
            st.error(body)
        elif lvl == "warning":
            st.warning(body)
        else:
            st.success(body)

    settings = load_settings()
    col_social, col_format, col_cat = st.columns([2, 2, 2])
    with col_social:
        platform = Platform(
            st.selectbox(
                "Social",
                options=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
                key="plan-platform",
            )
        )
    with col_format:
        plan_format = MediaFormat(
            st.selectbox(
                "Formato",
                options=[MediaFormat.POST.value, MediaFormat.STORY.value],
                format_func=media_format_label,
                key="plan-format",
            )
        )
    with col_cat:
        category_options = ["tutte"] + business_category_options
        selected_category = st.selectbox(
            "Categoria business",
            options=category_options,
            index=0,
            key="plan-category",
        )

    category_filter = None if selected_category == "tutte" else selected_category
    filter_key = f"{platform.value}|{plan_format.value}|{selected_category}"
    if st.session_state.get("plan-filter-key") != filter_key:
        st.session_state["plan-filter-key"] = filter_key
        st.session_state["plan-page-index"] = 0
        st.session_state["plan-selected-image-id"] = None
        st.session_state["plan-step"] = 1

    all_valid_ids = list_plannable_image_ids(
        settings_db_path,
        platform=platform,
        business_category=category_filter,
        media_format=plan_format,
        require_quality_pass=False,
        require_manual_publication_valid=True,
    )
    total = len(all_valid_ids)
    if total == 0:
        st.info(
            "Nessuna immagine approvata per questo social/formato. "
            "Elabora in **① Seleziona**, approva in **③ Approva**."
        )
        render_workflow_footer(4)
        return

    valid_set = set(all_valid_ids)
    raw_sel = st.session_state.get("plan-selected-image-id")
    selected_image_id: int | None = None
    if raw_sel is not None and int(raw_sel) in valid_set:
        selected_image_id = int(raw_sel)

    step = int(st.session_state.get("plan-step", 1))
    if step not in {1, 2}:
        step = 1
        st.session_state["plan-step"] = 1

    max_page = max(0, (total - 1) // _PLAN_IMAGE_PAGE_SIZE)

    if step == 1:
        _render_plan_step1(
            settings_db_path,
            settings=settings,
            platform=platform,
            plan_format=plan_format,
            category_filter=category_filter,
            total=total,
            max_page=max_page,
            selected_image_id=selected_image_id,
            plan_preview_dialog=plan_preview_dialog,
            render_copy_pack_preview=render_copy_pack_preview,
            media_format_label=media_format_label,
        )
        render_workflow_footer(4)
        return

    if selected_image_id is None:
        st.warning("Nessuna immagine selezionata.")
        if st.button("Torna allo Step 1", key="plan-back-no-selection"):
            st.session_state["plan-step"] = 1
            st.rerun()
        render_workflow_footer(4)
        return

    _render_plan_step2(
        settings_db_path,
        settings=settings,
        platform=platform,
        plan_format=plan_format,
        selected_image_id=selected_image_id,
        media_format_label=media_format_label,
        weekday_it=weekday_it,
        load_schedule_yaml=load_schedule_yaml,
        resolve_schedule_path=resolve_schedule_path,
    )
    render_workflow_footer(4)


def _render_plan_step1(
    settings_db_path: Path,
    *,
    settings: Any,
    platform: Platform,
    plan_format: MediaFormat,
    category_filter: str | None,
    total: int,
    max_page: int,
    selected_image_id: int | None,
    plan_preview_dialog: Any,
    render_copy_pack_preview: Any,
    media_format_label: Any,
) -> None:
    st.markdown("### Step 1 · Seleziona immagine")
    page_index = max(0, int(st.session_state.get("plan-page-index", 0)))
    if page_index > max_page:
        page_index = max_page
        st.session_state["plan-page-index"] = page_index

    nav_prev, nav_next, nav_info, _ = st.columns([1, 1, 4, 2])
    with nav_prev:
        if st.button("◀", disabled=page_index <= 0, key="plan-page-prev"):
            st.session_state["plan-page-index"] = max(0, page_index - 1)
            st.rerun()
    with nav_next:
        if st.button("▶", disabled=page_index >= max_page, key="plan-page-next"):
            st.session_state["plan-page-index"] = min(max_page, page_index + 1)
            st.rerun()
    with nav_info:
        sel_label = f"#{selected_image_id}" if selected_image_id else "nessuna"
        st.caption(
            f"Pagina {page_index + 1} di {max_page + 1} · {total} immagini · selezionata: {sel_label}"
        )

    options = list_plannable_images(
        settings_db_path,
        platform=platform,
        business_category=category_filter,
        limit=_PLAN_IMAGE_PAGE_SIZE,
        offset=page_index * _PLAN_IMAGE_PAGE_SIZE,
        media_format=plan_format,
        require_quality_pass=False,
        require_manual_publication_valid=True,
    )

    cols = st.columns(5)
    for i, row in enumerate(options):
        image_id = int(row["id"])
        image_name = str(row.get("name", "")).strip() or f"Immagine {image_id}"
        image_path = Path(str(row.get("path", "")))
        with cols[i % 5]:
            if image_path.is_file():
                st.image(str(image_path), caption=image_name, width="stretch")
                if st.button(
                    "Ingrandisci",
                    key=f"plan-preview-dlg-{page_index}-{image_id}",
                ):
                    plan_preview_dialog(str(image_path), image_name)
            else:
                st.caption(f"{image_name} (anteprima non disponibile)")
            picked = selected_image_id == image_id
            if st.button(
                "Selezionata" if picked else "Seleziona",
                key=f"plan-pick-btn-{page_index}-{image_id}",
                type="primary" if picked else "secondary",
            ):
                st.session_state["plan-selected-image-id"] = image_id
                st.session_state.pop("plan-detail", None)
                st.session_state.pop("plan-detail-source-id", None)
                st.rerun()

    if selected_image_id is None:
        st.info("Seleziona un'immagine per continuare.")
        return

    st.divider()
    st.markdown(f"#### Immagine #{selected_image_id}")

    copy_pack: dict[str, Any] | None = None
    if plan_format == MediaFormat.POST:
        col_obj, col_ch = st.columns(2)
        with col_obj:
            objective_value = st.selectbox(
                "Obiettivo contenuto",
                options=list(MARKETING_OBJECTIVES),
                key="plan-objective",
            )
        with col_ch:
            channels_value = st.multiselect(
                "Canali comunicazione",
                options=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
                format_func=lambda v: "Instagram" if v == Platform.INSTAGRAM.value else "Facebook",
                key="plan-channels",
            )
        if not channels_value:
            st.warning("Seleziona almeno un canale per generare il copy.")
        else:
            copy_pack = get_copy_pack(settings_db_path, image_id=selected_image_id)
            btn_label = "Rigenera copy" if copy_pack else "Genera copy"
            if st.button(btn_label, type="primary", key="plan-generate-copy"):
                try:
                    with st.spinner("Generazione copy in corso..."):
                        copy_pack = generate_copy_for_image(
                            selected_image_id,
                            platform=platform,
                            media_format=plan_format,
                            marketing_objective=normalize_marketing_objective(objective_value),
                            channels=normalize_channels(
                                channels_value,
                                fallback_platform=platform,
                            ),
                            settings=settings,
                        )
                    st.session_state.pop("plan-detail", None)
                    st.session_state.pop("plan-detail-source-id", None)
                    st.success("Copy generato.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            copy_pack = copy_pack or get_copy_pack(settings_db_path, image_id=selected_image_id)
            render_copy_pack_preview(copy_pack or {})

    can_continue = True
    if plan_format == MediaFormat.POST:
        copy_pack = copy_pack or get_copy_pack(settings_db_path, image_id=selected_image_id)
        can_continue = copy_pack is not None
    if st.button(
        "Continua allo Step 2 · Pianifica",
        type="primary",
        key="plan-go-step-2",
        disabled=not can_continue,
    ):
        st.session_state["plan-step"] = 2
        st.rerun()


def _render_plan_step2(
    settings_db_path: Path,
    *,
    settings: Any,
    platform: Platform,
    plan_format: MediaFormat,
    selected_image_id: int,
    media_format_label: Any,
    weekday_it: list[str],
    load_schedule_yaml: Any,
    resolve_schedule_path: Any,
) -> None:
    st.markdown("### Step 2 · Pianificazione")
    selected_rows = get_images_by_ids(settings_db_path, [selected_image_id])
    if not selected_rows:
        st.error("Immagine non trovata.")
        return
    row = selected_rows[0]
    image_path = Path(str(row.get("path", "")))
    image_name = str(row.get("name", "")).strip() or f"Immagine {selected_image_id}"

    if image_path.is_file():
        st.image(str(image_path), caption=f"#{selected_image_id} · {image_name}", width=320)

    story_sched_kind = "single"
    if plan_format == MediaFormat.STORY:
        story_sched_kind = st.radio(
            "Programmazione story",
            options=["single", "weekly"],
            format_func=lambda x: "Una data e ora"
            if x == "single"
            else "Ogni settimana (stesso giorno e ora)",
            horizontal=True,
            key="plan-story-sched-type",
        )

    plan_date = today_app(settings)
    plan_time = now_app(settings).time().replace(second=0, microsecond=0)
    story_weekday = 0
    story_slot_time = time(10, 0)
    story_tz = app_timezone_name(settings)

    if plan_format == MediaFormat.STORY and story_sched_kind == "weekly":
        cw1, cw2, cw3 = st.columns(3)
        with cw1:
            story_weekday = int(
                st.selectbox(
                    "Giorno",
                    options=list(range(7)),
                    format_func=lambda i: weekday_it[int(i)],
                    key="plan-story-wd",
                )
            )
        with cw2:
            story_slot_time = st.time_input("Ora", value=time(10, 0), key="plan-story-slot")
        with cw3:
            story_tz = st.text_input(
                "Fuso (IANA)",
                value=app_timezone_name(settings),
                key="plan-story-tz",
            )
    else:
        sched_path = resolve_schedule_path()
        if sched_path.is_file() and plan_format == MediaFormat.POST:
            try:
                schedule = load_schedule_yaml(sched_path)
                suggested = suggest_next_free_slot(
                    settings_db_path,
                    schedule,
                    platform=platform,
                )
                if suggested:
                    tz = ZoneInfo(schedule.timezone)
                    local_dt = suggested.scheduled_for.astimezone(tz)
                    wd_label = weekday_it[local_dt.weekday()]
                    st.info(
                        f"Prossimo slot libero: **{wd_label}** alle **{suggested.time_hhmm}** "
                        f"({schedule.timezone})"
                    )
                    if st.button("Usa questo slot", key="plan-use-editorial-slot"):
                        st.session_state["plan-date"] = local_dt.date()
                        st.session_state["plan-time"] = local_dt.time().replace(
                            second=0, microsecond=0
                        )
                        st.rerun()
            except Exception as exc:
                st.caption(f"Calendario editoriale: {exc}")
        col_d, col_t = st.columns(2)
        with col_d:
            plan_date = st.date_input("Data", value=today_app(settings), key="plan-date")
        with col_t:
            plan_time = st.time_input(
                "Ora",
                value=now_app(settings).time().replace(second=0, microsecond=0),
                key="plan-time",
            )

    detail = ""
    if plan_format == MediaFormat.STORY:
        st.caption("Le story si pubblicano solo come media, senza caption testuale.")
    else:
        if st.session_state.get("plan-detail-source-id") != selected_image_id:
            pack = get_copy_pack(settings_db_path, image_id=selected_image_id)
            cap = caption_for_platform(pack, platform=platform, media_format=plan_format)
            st.session_state["plan-detail"] = cap
            st.session_state["plan-detail-source-id"] = selected_image_id
        detail = st.text_area(
            "Caption per Meta",
            value="",
            key="plan-detail",
            height=120,
        )

    c_back, c_save = st.columns(2)
    if c_back.button("Torna allo Step 1", key="plan-back-step-1"):
        st.session_state["plan-step"] = 1
        st.rerun()

    if c_save.button("Salva pianificazione", type="primary"):
        try:
            settings_plan = load_settings()
            sched_kind = str(st.session_state.get("plan-story-sched-type", "single"))

            if plan_format == MediaFormat.STORY and sched_kind == "weekly":
                tz_clean = (story_tz or "").strip() or app_timezone_name(settings_plan)
                ZoneInfo(tz_clean)
                tl = f"{story_slot_time.hour:02d}:{story_slot_time.minute:02d}"
                add_story_schedule_rule(
                    settings_db_path,
                    image_id=selected_image_id,
                    platform=platform,
                    schedule_mode="weekly",
                    timezone_name=tz_clean,
                    weekday=int(story_weekday),
                    time_local=tl,
                    detail=None,
                )
                body = (
                    "Regola story ricorrente creata. Esegui **dispatch-scheduled** all'orario indicato."
                )
                st.session_state["plan_save_flash"] = {"level": "success", "body": body}
            else:
                scheduled_for = combine_app(plan_date, plan_time, settings_plan)
                pack = get_copy_pack(settings_db_path, image_id=selected_image_id)
                cap_from_pack = caption_for_platform(
                    pack,
                    platform=platform,
                    media_format=plan_format,
                )
                if plan_format == MediaFormat.POST and not (detail or "").strip() and not cap_from_pack:
                    raise ValueError("Genera il copy nello Step 1 prima di pianificare un post.")

                latest = latest_plan_for_image(
                    settings_db_path,
                    image_id=selected_image_id,
                    platform=platform,
                )
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
                if plan_format != MediaFormat.STORY:
                    cap_text = (detail or "").strip() or cap_from_pack
                    story_detail = planning_detail_with_caption(cap_text) or (cap_text or None)

                event_id = add_planning_event(
                    settings_db_path,
                    image_id=selected_image_id,
                    platform=platform,
                    event_type=event_type,
                    scheduled_for=scheduled_for,
                    detail=story_detail,
                )

                caption = (
                    ""
                    if plan_format == MediaFormat.STORY
                    else ((detail or "").strip() or cap_from_pack or image_name)
                )
                meta_fb_ok = 0
                ig_note = False
                meta_client: MetaClient | None = None
                if settings_plan.meta_page_access_token.strip():
                    meta_client = MetaClient(
                        settings_plan.meta_page_access_token.strip(),
                        settings_plan.meta_ig_user_id.strip(),
                        graph_version=(settings_plan.meta_graph_version or "v22.0").strip(),
                        settings=settings_plan,
                    )

                resolved = resolve_media_file_path(str(row.get("path", "")))
                image_file = resolved if resolved is not None else image_path

                if (
                    meta_client is not None
                    and platform == Platform.FACEBOOK
                    and plan_format == MediaFormat.POST
                ):
                    if not image_file.is_file():
                        raise ValueError("File immagine assente sul disco.")
                    if prev_ext:
                        try:
                            meta_client.delete_graph_object(prev_ext)
                        except Exception as exc:
                            raise ValueError(
                                f"Eliminazione programmazione Meta precedente fallita: {exc}"
                            ) from exc
                    ext_id = meta_client.schedule_facebook_photo(
                        image_file,
                        caption,
                        publish_at=scheduled_for,
                    )
                    update_planning_event_external_id(
                        settings_db_path,
                        event_id=event_id,
                        external_id=ext_id,
                    )
                    meta_fb_ok = 1
                elif platform == Platform.INSTAGRAM:
                    ig_note = True

                lines = [f"Pianificazione salvata per #{selected_image_id}."]
                if meta_fb_ok:
                    lines.append("Programmazione nativa su Meta (Facebook Page) creata.")
                extra = ""
                if plan_format == MediaFormat.STORY and sched_kind == "single":
                    extra = (
                        "\n\nStory: orario salvato nel database. Usa **dispatch-scheduled** "
                        "all'orario per pubblicare."
                    )
                elif platform == Platform.INSTAGRAM and ig_note and plan_format == MediaFormat.POST:
                    extra = (
                        "\n\nInstagram: data salvata nel database. Usa **dispatch-scheduled** "
                        "all'orario pianificato."
                    )
                st.session_state["plan_save_flash"] = {
                    "level": "success",
                    "body": "\n".join(lines) + extra,
                }
        except Exception as exc:
            st.session_state["plan_save_flash"] = {
                "level": "error",
                "body": f"Salvataggio fallito: {exc}",
            }
        st.rerun()
