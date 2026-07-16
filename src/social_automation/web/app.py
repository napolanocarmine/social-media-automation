"""Streamlit FE: processa foto + calendario pianificazione."""

from __future__ import annotations

import calendar
import json
import mimetypes
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image

from social_automation.app_timezone import (
    format_hhmm_local,
    month_bounds_local,
    now_app,
    parse_iso_datetime,
    today_app,
)
from social_automation.brand.prompt_context import (
    MARKETING_OBJECTIVES,
)
from social_automation.canva.client import CanvaClient
from social_automation.canva.templates import resolve_template_id
from social_automation.config_loaders import (
    load_canva_yaml,
    load_category_aliases,
    load_schedule_yaml,
    resolve_drive_folder_id,
    resolve_schedule_path,
)
from social_automation.db.store import (
    add_batch_item,
    count_images_for_manual_publication_review,
    create_batch,
    finalize_batch,
    get_batch,
    latest_metadata_for_image,
    list_ai_output_images,
    list_batch_items,
    list_batches,
    list_calendar_items,
    list_due_events,
    list_images_for_manual_publication_review,
    mark_batch_runner_pid,
    record_render_artifacts,
    request_batch_stop,
    set_image_manual_publication_valid,
)
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import (
    normalize_business_category,
)
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.processing.image_adjust import normalize_image_file
from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.scheduling.prepare_week import prepare_week
from social_automation.scheduling.story_rules_dispatch import collect_due_story_rules
from social_automation.services.dashboard import get_workflow_stats as _workflow_stats
from social_automation.services.dashboard import suggest_next_page as _suggest_next_page
from social_automation.services.drive_selection import (
    DEFAULT_CATEGORIES_CONFIG as _DEFAULT_CATEGORIES_CONFIG,
)
from social_automation.services.drive_selection import (
    business_category_options as _business_category_options,
)
from social_automation.services.drive_selection import (
    load_drive_assets_for_selection as _load_drive_assets_for_selection,
)
from social_automation.services.drive_selection import pick_latest_asset as _pick_latest_asset
from social_automation.services.process_photo import run_process_photo as _run_process_photo
from social_automation.services.project_paths import project_root as _project_root
from social_automation.settings import load_settings
from social_automation.web.calendar_edit_ui import render_calendar_edit_section
from social_automation.web.plan_image_ui import render_plan_image_page
from social_automation.workflow.process_photo import revert_image_to_original

_APPROVAL_PAGE_SIZE = 20
_DRIVE_SELECT_PAGE_SIZE = 12
_MONTH_NAME_IT = {
    1: "Gennaio",
    2: "Febbraio",
    3: "Marzo",
    4: "Aprile",
    5: "Maggio",
    6: "Giugno",
    7: "Luglio",
    8: "Agosto",
    9: "Settembre",
    10: "Ottobre",
    11: "Novembre",
    12: "Dicembre",
}


_PLATFORM_LABELS: dict[str, str] = {
    Platform.INSTAGRAM.value: "Instagram",
    Platform.FACEBOOK.value: "Facebook",
}

_MEDIA_FORMAT_LABELS: dict[str, str] = {
    MediaFormat.POST.value: "Post (feed)",
    MediaFormat.STORY.value: "Story (verticale 9:16)",
}

_WEEKDAY_IT: list[str] = [
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
]


def _platform_label(value: str) -> str:
    return _PLATFORM_LABELS.get(value, value)


def _media_format_label(value: str) -> str:
    return _MEDIA_FORMAT_LABELS.get(value, value)


@st.dialog("Anteprima immagine", width="large")
def _plan_step1_image_preview_dialog(image_path_str: str, caption: str) -> None:
    """Mostra il file raster a piena risoluzione (non la miniatura 140px)."""
    p = Path(image_path_str)
    if not p.is_file():
        st.error("File immagine non trovato.")
        return
    with Image.open(p) as im:
        w, h = im.size
        st.caption(f"Dimensioni originali: {w}×{h} px · {p.name}")
        st.image(im.convert("RGB"), caption=caption, width="stretch")


def _ensure_ui_state_defaults() -> None:
    st.session_state.setdefault("render-category", "food")
    st.session_state.setdefault("render-platform", Platform.INSTAGRAM.value)
    st.session_state.setdefault("render-format", MediaFormat.POST.value)
    st.session_state.setdefault("plan-objective", MARKETING_OBJECTIVES[1])
    st.session_state.setdefault(
        "plan-channels",
        [Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
    )
    st.session_state.setdefault("calendar-social", "tutti")
    st.session_state.setdefault("calendar-category", "tutte")
    st.session_state.setdefault("plan-platform", Platform.INSTAGRAM.value)
    st.session_state.setdefault("plan-format", MediaFormat.POST.value)
    st.session_state.setdefault("plan-category", "tutte")
    st.session_state.setdefault("plan-step", 1)
    st.session_state.setdefault("plan-selected-image-id", None)
    st.session_state.setdefault("plan-page-index", 0)
    st.session_state.setdefault("plan-filter-key", "")
    st.session_state.setdefault("render-active-batch-id", None)
    st.session_state.setdefault("batch-dashboard-status", "tutti")
    st.session_state.setdefault("batch-dashboard-platform", "tutti")
    st.session_state.setdefault("batch-dashboard-format", "tutti")
    st.session_state.setdefault("batch-dashboard-limit", 50)
    st.session_state.setdefault("batch-dashboard-selected-id", None)
    st.session_state.setdefault("render-batch-last-toast-key", "")
    st.session_state.setdefault("approve-platform", Platform.INSTAGRAM.value)
    st.session_state.setdefault("approve-format", MediaFormat.POST.value)
    st.session_state.setdefault("approve-category", "tutte")
    st.session_state.setdefault("approve-page-index", 0)
    st.session_state.setdefault("approve-filter-key", "")
    st.session_state.setdefault("drive-asset-list", [])
    st.session_state.setdefault("drive-selected-ids", [])
    st.session_state.setdefault("drive-select-page-index", 0)
    st.session_state.setdefault("ai-output-filter", "pending")
    st.session_state.setdefault("ui-page", "Home")


_UI_PAGES: list[str] = [
    "Home",
    "① Seleziona",
    "② Output AI",
    "③ Approva",
    "④ Pianifica",
    "⑤ Pubblica",
    "Automazione",
]

_WORKFLOW_STEPS: dict[str, int] = {
    "① Seleziona": 1,
    "② Output AI": 2,
    "③ Approva": 3,
    "④ Pianifica": 4,
    "⑤ Pubblica": 5,
}


def _go_to_page(page: str) -> None:
    if page in _UI_PAGES:
        st.session_state["ui-page"] = page
        st.rerun()


def _current_ui_page() -> str:
    page = str(st.session_state.get("ui-page", "Home"))
    return page if page in _UI_PAGES else "Home"


def _render_workflow_step_header(step: int | None, title: str) -> None:
    labels = ["Seleziona", "Output AI", "Approva", "Pianifica", "Pubblica"]
    cols = st.columns(5)
    page_by_step = {
        1: "① Seleziona",
        2: "② Output AI",
        3: "③ Approva",
        4: "④ Pianifica",
        5: "⑤ Pubblica",
    }
    for i, label in enumerate(labels, start=1):
        with cols[i - 1]:
            active = step == i
            if st.button(
                f"{'● ' if active else ''}{i}. {label}",
                key=f"wf-nav-{step}-{i}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                _go_to_page(page_by_step[i])
    st.subheader(title)


def _render_workflow_footer(step: int) -> None:
    st.divider()
    left, mid, right = st.columns(3)
    nav = {
        1: "① Seleziona",
        2: "② Output AI",
        3: "③ Approva",
        4: "④ Pianifica",
        5: "⑤ Pubblica",
    }
    with left:
        if step > 1 and st.button("← Indietro", key=f"wf-back-{step}"):
            _go_to_page(nav[step - 1])
    with mid:
        if st.button("Home", key=f"wf-home-{step}"):
            _go_to_page("Home")
    with right:
        if step < 5 and st.button("Avanti →", key=f"wf-fwd-{step}", type="primary"):
            _go_to_page(nav[step + 1])


def _render_home_page(db_path: Path, settings: Any) -> None:
    st.subheader("Dashboard")
    st.caption(
        "Flusso Story: **Drive → ritocco AI → approvazione foto → copy in pianificazione → Meta**."
    )
    stats = _workflow_stats(db_path, settings)
    next_page = _suggest_next_page(stats)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Foto elaborate", stats["processed_visual"])
    c2.metric("Da approvare", stats["pending_approval"])
    c3.metric("Pronte da pianificare", stats["ready_to_plan"])
    c4.metric("Da pubblicare (scaduti)", stats["due_dispatch"])
    c5.metric("Batch attivi", stats["running_batches"])

    st.info(f"**Prossimo passo consigliato:** {next_page}")
    if st.button(f"Vai a {next_page}", type="primary", key="home-next"):
        _go_to_page(next_page)

    st.markdown("#### Percorso rapido")
    q1, q2, q3, q4, q5 = st.columns(5)
    with q1:
        if st.button("① Seleziona", use_container_width=True, key="home-q-select"):
            _go_to_page("① Seleziona")
    with q2:
        if st.button("② Output AI", use_container_width=True, key="home-q-output"):
            _go_to_page("② Output AI")
    with q3:
        if st.button("③ Approva", use_container_width=True, key="home-q-approve"):
            _go_to_page("③ Approva")
    with q4:
        if st.button("④ Pianifica", use_container_width=True, key="home-q-plan"):
            _go_to_page("④ Pianifica")
    with q5:
        if st.button("⑤ Pubblica", use_container_width=True, key="home-q-dispatch"):
            _go_to_page("⑤ Pubblica")

    with st.expander("Automazione settimanale", expanded=False):
        st.caption(
            "Prepara l'intera settimana in un colpo solo (processa, approva, pianifica slot)."
        )
        if st.button("Apri Automazione", key="home-open-auto"):
            _go_to_page("Automazione")


def _format_eta(seconds: float) -> str:
    sec = max(0, int(round(seconds)))
    mins, rem = divmod(sec, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}h {mins:02d}m"
    if mins > 0:
        return f"{mins}m {rem:02d}s"
    return f"{rem}s"


def _status_badge_html(status: str) -> str:
    val = (status or "").strip().lower()
    bg = "#6b7280"
    if val == "completed":
        bg = "#16a34a"
    elif val == "running":
        bg = "#2563eb"
    elif val == "partial":
        bg = "#d97706"
    elif val == "failed":
        bg = "#dc2626"
    elif val == "cancelled":
        bg = "#7c3aed"
    label = val or "unknown"
    return (
        "<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"background:{bg};color:#fff;font-size:0.8rem;font-weight:600'>{label}</span>"
    )


def _launch_background_batch_job(
    *,
    batch_id: int,
    category: str,
    platform: Platform,
    total: int,
    target_year: int | None = None,
    target_month: int | None = None,
    media_format: MediaFormat = MediaFormat.POST,
) -> int:
    cmd = [
        sys.executable,
        "-m",
        "social_automation.web.batch_job_runner",
        "--batch-id",
        str(int(batch_id)),
        "--category",
        category.strip(),
        "--platform",
        platform.value,
        "--total",
        str(max(0, int(total))),
        "--media-format",
        media_format.value,
    ]
    if target_year is not None:
        cmd.extend(["--target-year", str(int(target_year))])
    if target_month is not None:
        cmd.extend(["--target-month", str(int(target_month))])
    proc = subprocess.Popen(
        cmd,
        cwd=str(_project_root()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return int(proc.pid)


def _render_batch_live_status(settings_db_path: Path, batch_id: int) -> None:
    row = get_batch(settings_db_path, batch_id=batch_id)
    if row is None:
        st.warning(f"Batch {batch_id} non trovato.")
        return
    requested = int(row.get("requested_count", 0) or 0)
    completed = int(row.get("completed_count", 0) or 0)
    failed = int(row.get("failed_count", 0) or 0)
    done = completed + failed
    status = str(row.get("status", "")).strip().lower() or "unknown"
    pct = int((done / requested) * 100) if requested > 0 else 0
    progress_value = (done / requested) if requested > 0 else 0.0
    st.caption(
        f"Batch attivo #{batch_id} · stato={status} · "
        f"completati={completed} · errori={failed} · pid={row.get('runner_pid')}"
    )
    st.progress(
        progress_value,
        text=f"Avanzamento batch: {pct}% ({done}/{requested})",
    )
    last_error = str(row.get("last_error", "") or "").strip()
    if last_error:
        st.caption(f"Ultimo errore: {last_error}")
    stop_requested_at = str(row.get("stop_requested_at", "") or "").strip()
    if stop_requested_at:
        stop_reason = str(row.get("stop_reason", "") or "").strip()
        if stop_reason:
            st.caption(f"Stop richiesto: {stop_reason}")
        else:
            st.caption("Stop richiesto: in attesa di arresto runner.")


def _maybe_toast_batch_status(settings_db_path: Path, batch_id: int) -> None:
    row = get_batch(settings_db_path, batch_id=batch_id)
    if row is None:
        return
    status = str(row.get("status", "") or "").strip().lower() or "unknown"
    toast_key = f"{batch_id}:{status}"
    if st.session_state.get("render-batch-last-toast-key") == toast_key:
        return
    if status == "running":
        st.toast(f"Batch #{batch_id} creato ed in running.", icon="⏳")
    elif status == "failed":
        st.toast(f"Batch #{batch_id} fallito.", icon="❌")
    elif status == "cancelled":
        st.toast(f"Batch #{batch_id} interrotto manualmente.", icon="🛑")
    elif status == "completed":
        st.toast(f"Batch #{batch_id} completato.", icon="✅")
    elif status == "partial":
        st.toast(f"Batch #{batch_id} completato parzialmente.", icon="⚠️")
    st.session_state["render-batch-last-toast-key"] = toast_key


def _render_batch_dashboard(settings_db_path: Path) -> None:
    st.subheader("Monitor batch")
    if st.button("Apri ultimo batch running", key="open-latest-running-batch"):
        latest_running = list_batches(
            settings_db_path,
            status="running",
            platform=None,
            limit=1,
        )
        if not latest_running:
            st.info("Nessun batch running al momento.")
        else:
            st.session_state["batch-dashboard-status"] = "running"
            st.session_state["batch-dashboard-platform"] = "tutti"
            st.session_state["batch-dashboard-selected-id"] = int(latest_running[0]["id"])
            st.rerun()

    col_s, col_p, col_f, col_l = st.columns([2, 2, 2, 1])
    with col_s:
        status_filter = st.selectbox(
            "Stato",
            options=["tutti", "running", "completed", "partial", "failed", "cancelled"],
            key="batch-dashboard-status",
        )
    with col_p:
        platform_value = st.selectbox(
            "Social",
            options=["tutti", Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
            key="batch-dashboard-platform",
        )
    with col_f:
        format_value = st.selectbox(
            "Formato",
            options=["tutti", MediaFormat.POST.value, MediaFormat.STORY.value],
            format_func=lambda v: "Tutti" if v == "tutti" else _media_format_label(v),
            key="batch-dashboard-format",
        )
    with col_l:
        max_rows = int(
            st.selectbox(
                "Max righe",
                options=[20, 50, 100, 200],
                index=1,
                key="batch-dashboard-limit",
            )
        )
    platform = None if platform_value == "tutti" else Platform(platform_value)
    status = None if status_filter == "tutti" else status_filter
    media_format_filter = (
        None if format_value == "tutti" else MediaFormat(format_value)
    )
    rows = list_batches(
        settings_db_path,
        status=status,
        platform=platform,
        limit=max_rows,
        media_format=media_format_filter,
    )
    if not rows:
        st.info("Nessun batch disponibile con i filtri correnti.")
        return
    st.caption(f"Batch trovati: {len(rows)}")
    table_rows: list[dict[str, Any]] = []
    for r in rows:
        rr = dict(r)
        requested = max(1, int(rr.get("requested_count", 0) or 0))
        done = int(rr.get("completed_count", 0) or 0) + int(rr.get("failed_count", 0) or 0)
        rr["progress_pct"] = int((done / requested) * 100)
        rr["media_format"] = (
            str(rr.get("media_format") or "").strip().lower()
            or MediaFormat.POST.value
        )
        table_rows.append(rr)
    st.dataframe(table_rows, width="stretch", hide_index=True)
    labels = [
        f"#{r['id']} · {r['status']} · {r['category']} · {r['platform']} · "
        f"{r.get('media_format') or MediaFormat.POST.value}"
        for r in rows
    ]
    default_idx = 0
    selected_batch_id = st.session_state.get("batch-dashboard-selected-id")
    if isinstance(selected_batch_id, int):
        for i, r in enumerate(rows):
            if int(r["id"]) == selected_batch_id:
                default_idx = i
                break
    selected_label = st.selectbox(
        "Dettaglio batch",
        options=labels,
        index=default_idx,
        key="batch-dashboard-selected",
    )
    selected_idx = labels.index(selected_label)
    selected = rows[selected_idx]
    batch_id = int(selected["id"])
    st.session_state["batch-dashboard-selected-id"] = batch_id
    st.markdown(
        f"**Batch #{batch_id}** — stato {_status_badge_html(str(selected['status']))} · "
        f"richiesti `{selected['requested_count']}` · "
        f"completati `{selected['completed_count']}` · errori `{selected['failed_count']}`",
        unsafe_allow_html=True,
    )
    selected_status = str(selected.get("status", "")).strip().lower()
    if selected_status == "running":
        stop_reason = st.text_input(
            "Motivo stop batch (opzionale)",
            value="",
            key=f"batch-stop-reason-{batch_id}",
            placeholder="Es. stop manuale operatore / verifica configurazione",
        )
        if st.button("Stop batch", key=f"batch-stop-btn-{batch_id}", type="secondary"):
            requested = request_batch_stop(
                settings_db_path,
                batch_id=batch_id,
                reason=stop_reason,
            )
            if requested:
                st.warning(
                    f"Stop richiesto per batch #{batch_id}. "
                    "Il runner chiudera` il batch al prossimo checkpoint."
                )
            else:
                st.info(
                    f"Impossibile richiedere stop per batch #{batch_id}: "
                    "batch non running o gia` terminato."
                )
            st.rerun()
    _render_batch_live_status(settings_db_path, batch_id)
    item_rows = list_batch_items(settings_db_path, batch_id=batch_id, limit=5000)
    if not item_rows:
        st.caption("Nessun item registrato per questo batch.")
    else:
        st.caption(f"Item batch: {len(item_rows)}")
        st.dataframe(item_rows, width="stretch", hide_index=True)
    if st.button("Aggiorna dashboard batch", key="refresh-batch-dashboard"):
        st.rerun()


def _drive_asset_label(asset: DriveAsset) -> str:
    path_hint = "/".join(asset.path_segments[-3:]) if asset.path_segments else ""
    suffix = f" · {path_hint}" if path_hint else ""
    return f"{asset.name}{suffix}"


def _drive_cache_path(settings: Any, file_id: str, mime_type: str) -> Path:
    ext = mimetypes.guess_extension(mime_type) or ".jpg"
    # sottocartella exif/ invalida cache pre-fix orientamento
    return settings.output_dir / "drive_cache" / "exif" / f"{file_id}{ext}"


def _clear_legacy_drive_cache(settings: Any) -> None:
    """Rimuove anteprime cache senza correzione EXIF (path legacy)."""
    legacy_dir = settings.output_dir / "drive_cache"
    exif_dir = legacy_dir / "exif"
    if not legacy_dir.is_dir():
        return
    for entry in legacy_dir.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def _clear_drive_thumb_cache(settings: Any) -> None:
    """Svuota cache anteprime EXIF (rigenera orientamento al prossimo scroll)."""
    exif_dir = settings.output_dir / "drive_cache" / "exif"
    if not exif_dir.is_dir():
        return
    for entry in exif_dir.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
            except OSError:
                pass


def _get_drive_thumb(
    settings: Any,
    drive_client: DriveClient,
    *,
    file_id: str,
    mime_type: str,
) -> Path | None:
    """Scarica e cachea miniatura Drive con orientamento EXIF corretto."""
    cache_path = _drive_cache_path(settings, file_id, mime_type)
    if cache_path.is_file():
        return cache_path
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(drive_client.download_file_bytes(file_id))
        normalize_image_file(cache_path)
        return cache_path
    except Exception:
        return None


def _launch_selected_ai_batch_job(*, batch_id: int, queue_file: Path) -> int:
    cmd = [
        sys.executable,
        "-m",
        "social_automation.web.selected_ai_batch_runner",
        "--batch-id",
        str(int(batch_id)),
        "--queue-file",
        str(queue_file),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(_project_root()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return int(proc.pid)


def _parse_copy_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _render_copy_pack_preview(copy_data: dict[str, Any]) -> None:
    """Anteprima copy pack generato in Pianifica."""
    if not copy_data:
        st.info("Nessun copy generato. Usa **Genera copy**.")
        return
    ig = str(copy_data.get("instagram_caption") or "").strip()
    fb = str(copy_data.get("facebook_caption") or "").strip()
    story = str(copy_data.get("story_text") or "").strip()
    cta = str(copy_data.get("cta") or "").strip()
    tags = copy_data.get("hashtags") or []
    if isinstance(tags, list):
        tags_line = " ".join(str(t).strip() for t in tags if str(t).strip())
    else:
        tags_line = str(tags).strip()
    if ig:
        st.markdown(f"**Instagram:** {ig}")
    if fb:
        st.markdown(f"**Facebook:** {fb}")
    if story:
        st.markdown(f"**Story text:** {story}")
    if cta:
        st.markdown(f"**CTA:** {cta}")
    if tags_line:
        st.markdown(f"**Hashtag:** {tags_line}")
    review = copy_data.get("final_review") or {}
    if isinstance(review, dict) and review.get("notes"):
        st.caption(f"Review AI: {review.get('notes')}")


def _render_before_after_row(
    *,
    source_path: str | None,
    processed_path: Path,
    caption_text: str = "",
    visual_score: float | None = None,
    visual_status: str | None = None,
    editing_required: bool | None = None,
    copy_data: dict[str, Any] | None = None,
    show_full_copy: bool = False,
) -> None:
    if visual_score is not None or visual_status:
        cols = st.columns(4)
        if visual_score is not None:
            cols[0].metric("Visual Score", f"{visual_score:.1f}")
        if visual_status:
            cols[1].caption(f"**Status:** `{visual_status}`")
        if editing_required is not None:
            cols[2].caption(
                f"**Editing:** {'sì' if int(editing_required) == 1 else 'no'}"
            )
    col_before, col_after = st.columns(2)
    with col_before:
        st.caption("Originale Drive")
        src = Path(source_path) if source_path else None
        if src and src.is_file():
            st.image(str(src), use_container_width=True)
        else:
            st.caption("Originale non in cache locale")
    with col_after:
        st.caption("Asset finale")
        if processed_path.is_file():
            st.image(str(processed_path), use_container_width=True)
        else:
            st.caption("File output assente")
    if show_full_copy and copy_data:
        ig = str(copy_data.get("instagram_caption") or "").strip()
        fb = str(copy_data.get("facebook_caption") or "").strip()
        story = str(copy_data.get("story_text") or "").strip()
        cta = str(copy_data.get("cta") or "").strip()
        tags = copy_data.get("hashtags") or []
        if isinstance(tags, list):
            tags_line = " ".join(str(t).strip() for t in tags if str(t).strip())
        else:
            tags_line = str(tags).strip()
        if ig:
            st.markdown(f"**Caption Instagram:** {ig}")
        if fb:
            st.markdown(f"**Caption Facebook:** {fb}")
        if story:
            st.markdown(f"**Story text:** {story}")
        if cta:
            st.markdown(f"**CTA:** {cta}")
        if tags_line:
            st.markdown(f"**Hashtag:** {tags_line}")
    elif caption_text.strip():
        st.markdown(f"**Caption:** {caption_text.strip()}")


def _run_render(
    *,
    category: str,
    platform: Platform,
    target_year: int | None = None,
    target_month: int | None = None,
    media_format: MediaFormat = MediaFormat.POST,
) -> dict[str, Any]:
    settings = load_settings()
    categories_config = _DEFAULT_CATEGORIES_CONFIG
    canva_config = settings.canva_config_path
    folder_id = resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env=settings.google_drive_folder_id,
        categories_yaml=categories_config,
    )
    if not folder_id:
        raise RuntimeError(
            "Manca folder id Drive: compila il campo o usa GOOGLE_DRIVE_FOLDER_ID/"
            "drive_root_folder_id nel file categorie."
        )
    if not canva_config.exists():
        raise RuntimeError(f"Config Canva non trovata: {canva_config}")

    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive_client = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=True,
        oauth_browser=oauth_browser,
    )
    selected, aliases = _pick_latest_asset(
        drive_client,
        folder_id,
        category=category,
        categories_config=categories_config,
        db_path=settings.db_path,
        platform=platform,
        target_year=target_year,
        target_month=target_month,
        media_format=media_format,
    )
    business_category = normalize_business_category(category, aliases)

    canva_cfg = load_canva_yaml(canva_config)
    template_id = resolve_template_id(
        canva_cfg,
        platform=platform.value,
        category=business_category,
        media_format=media_format,
    )
    if not template_id:
        raise RuntimeError(
            f"Nessun template Canva configurato per platform={platform.value} "
            f"category={business_category} format={media_format.value}."
        )

    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
    source_path = output_dir / f"drive_{selected.file_id}{suffix}"
    source_path.write_bytes(drive_client.download_file_bytes(selected.file_id))

    canva_client = CanvaClient.from_token_file(
        settings.canva_client_id.strip(),
        settings.canva_client_secret.strip(),
        settings.canva_redirect_uri.strip(),
        settings.canva_token_path,
    )
    rendered = canva_client.render_for_platform(
        source_path,
        platform,
        template_id=template_id,
        output_dir=output_dir / "canva-rendered",
        output_stem=f"{business_category}_{selected.file_id}",
        use_placeholder=False,
        precrop_cover=True,
        media_format=media_format,
    )
    render_metadata = canva_client.get_last_render_metadata() or {}
    db_image_id = record_render_artifacts(
        settings.db_path,
        image_name=selected.name,
        image_path=rendered,
        source_asset_id=selected.file_id,
        source_asset_name=selected.name,
        business_category=business_category,
        metadata_payload=render_metadata,
    )
    return {
        "selected_asset": f"{selected.file_id}\t{selected.name}",
        "source_asset_id": selected.file_id,
        "source_asset_name": selected.name,
        "business_category": business_category,
        "platform": platform.value,
        "media_format": media_format.value,
        "template_id": template_id,
        "rendered_file": str(rendered),
        "rendered_name": rendered.name,
        "db_image_id": str(db_image_id),
    }


def _run_render_batch(
    *,
    category: str,
    platform: Platform,
    batch_size: int,
    target_year: int | None = None,
    target_month: int | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    media_format: MediaFormat = MediaFormat.POST,
) -> dict[str, Any]:
    """Esegue più render sequenziali; si ferma quando termina input o su errore."""
    settings = load_settings()
    total = max(0, int(batch_size))
    if total == 0:
        return {
            "batch_id": None,
            "status": "completed",
            "results": [],
            "errors": [],
        }
    batch_id = create_batch(
        settings.db_path,
        category=category,
        platform=platform,
        requested_count=total,
        media_format=media_format,
    )
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    completed_count = 0
    failed_count = 0
    final_status = "completed"
    last_error: str | None = None
    for idx in range(total):
        item_idx = idx + 1
        try:
            result = _run_process_photo(
                category=category,
                platform=platform,
                target_year=target_year,
                target_month=target_month,
                media_format=media_format,
            )
        except Exception as e:
            msg = str(e).strip() or repr(e)
            is_no_more_assets = "Nessun asset trovato" in msg
            if is_no_more_assets:
                errors.append(
                    "Batch terminato in anticipo: non ci sono altre immagini "
                    "non ancora renderizzate per questa categoria/social/formato."
                )
                add_batch_item(
                    settings.db_path,
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
                final_status = "partial" if results else "failed"
                if not results:
                    failed_count += 1
                    last_error = msg
                break
            failed_count += 1
            last_error = msg
            add_batch_item(
                settings.db_path,
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
            errors.append(msg)
            final_status = "failed"
            break
        results.append(result)
        completed_count += 1
        add_batch_item(
            settings.db_path,
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
        if on_progress is not None:
            on_progress(item_idx, total, str(result.get("rendered_name", "")))
    if final_status == "completed" and completed_count < total:
        final_status = "partial"
    finalize_batch(
        settings.db_path,
        batch_id=batch_id,
        status=final_status,
        completed_count=completed_count,
        failed_count=failed_count,
        last_error=last_error,
    )
    return {
        "batch_id": batch_id,
        "status": final_status,
        "results": results,
        "errors": errors,
    }


def _list_rendered_images(root: Path, subdir: str, *, limit: int = 12) -> list[Path]:
    target = root / subdir
    if not target.exists():
        return []
    files = [
        p
        for p in target.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _render_gallery(root: Path, subdir: str) -> None:
    files = _list_rendered_images(root, subdir)
    if not files:
        st.caption("Nessun render disponibile")
        return
    cols = st.columns(3)
    for i, img in enumerate(files):
        cols[i % 3].image(str(img), caption=img.name)


def _calendar_month_bounds(
    year: int,
    month: int,
    settings: Any | None = None,
) -> tuple[datetime, datetime]:
    return month_bounds_local(year, month, settings)


def _events_by_day(
    items: list[dict[str, Any]],
    settings: Any | None = None,
) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for row in items:
        raw = str(row.get("scheduled_for", "")).strip()
        if not raw:
            continue
        dt = parse_iso_datetime(raw, settings)
        if dt is None:
            continue
        out.setdefault(dt.day, []).append(row)
    for day in out:
        out[day].sort(key=lambda r: str(r.get("scheduled_for", "")))
    return out


def _render_planning_calendar(settings_db_path: Path) -> None:
    settings = load_settings()
    today = today_app(settings)
    col_m, col_s, col_c, col_l = st.columns([2, 2, 2, 1])
    with col_m:
        month_start = st.date_input(
            "Mese calendario",
            value=date(today.year, today.month, 1),
            format="YYYY-MM-DD",
        )
    with col_s:
        social_options = ["tutti", Platform.INSTAGRAM.value, Platform.FACEBOOK.value]
        selected_social = st.selectbox(
            "Social",
            options=social_options,
            index=0,
            key="calendar-social",
        )
    with col_c:
        category_options = ["tutte"] + _business_category_options(
            _DEFAULT_CATEGORIES_CONFIG
        )
        selected_category = st.selectbox(
            "Categoria business",
            options=category_options,
            index=0,
            key="calendar-category",
        )
    with col_l:
        max_items = int(
            st.selectbox(
                "Max elementi",
                options=[200, 500, 1000],
                index=1,
            )
        )

    year = int(month_start.year)
    month = int(month_start.month)
    start_dt, end_dt = _calendar_month_bounds(year, month, settings)
    platform_filter = (
        None if selected_social == "tutti" else Platform(selected_social)
    )
    category_filter = None if selected_category == "tutte" else selected_category
    items = list_calendar_items(
        settings_db_path,
        start_inclusive=start_dt,
        end_exclusive=end_dt,
        platform=platform_filter,
        business_category=category_filter,
        limit=max_items,
    )
    grouped = _events_by_day(items, settings)

    st.caption(f"Eventi pianificati nel mese: {len(items)}")
    week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    headers = st.columns(7)
    for i, d in enumerate(week_days):
        headers[i].markdown(f"**{d}**")

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdayscalendar(year, month):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                with st.container(border=True):
                    if day == 0:
                        st.markdown("&nbsp;", unsafe_allow_html=True)
                        continue
                    st.markdown(f"**{day}**")
                    events = grouped.get(day, [])
                    if not events:
                        st.caption("—")
                        continue
                    for ev in events[:2]:
                        platform = str(ev.get("platform", "")).upper()
                        when = str(ev.get("scheduled_for", ""))
                        hhmm = format_hhmm_local(when, settings)
                        st.caption(f"{platform} · {hhmm}")
                        img = Path(str(ev.get("image_path", "")))
                        if img.is_file():
                            st.image(str(img), width="stretch")
                        else:
                            st.caption("Anteprima non disponibile")
                    if len(events) > 2:
                        st.caption(f"+{len(events) - 2} altri")

    st.divider()
    render_calendar_edit_section(
        settings_db_path,
        settings=settings,
        month_items=items,
        platform_filter=platform_filter,
    )


def _render_prepare_week_page(settings_db_path: Path) -> None:
    st.caption(
        "Per ogni slot libero in `config/schedule.yaml`: processa foto mancanti, "
        "auto-approva se Story AI OK, pianifica con caption."
    )
    settings = load_settings()
    sched_path = resolve_schedule_path(settings.schedule_config_path)
    if not sched_path.is_file():
        st.error(
            "Calendario editoriale non trovato. Copia "
            "`config/schedule.example.yaml` in `config/schedule.yaml`."
        )
        return
    st.caption(f"Schedule: `{sched_path}`")
    days = int(st.selectbox("Giorni da coprire", options=[7, 14, 21], index=0, key="pw-days"))
    dry_run = st.checkbox("Solo simulazione (dry-run)", value=True, key="pw-dry-run")
    try_render = st.checkbox(
        "Tenta processamento Drive→Story AI se mancano immagini",
        value=True,
        key="pw-render",
    )
    if st.button("Avvia preparazione settimanale", type="primary", key="pw-run"):
        try:
            with st.spinner("Preparazione in corso..."):
                result = prepare_week(
                    schedule_path=sched_path,
                    settings=settings,
                    days=days,
                    dry_run=dry_run,
                    try_render=try_render and not dry_run,
                )
        except Exception as exc:
            st.error(str(exc))
            st.exception(exc)
            return
        st.success(
            f"Completato: pianificati={result.planned}, render={result.rendered}, "
            f"auto-approvati={result.auto_approved}, vision={result.vision_evaluated}"
        )
        if result.assignments:
            st.dataframe(result.assignments, width="stretch", hide_index=True)
        if result.errors:
            for err in result.errors:
                st.warning(err)
        if result.skipped_borderline:
            st.info(
                f"{result.skipped_borderline} immagine/i da rivedere: "
                "vai a **② Approva**."
            )
        if not dry_run and result.planned > 0:
            if st.button("Vai a ⑤ Pubblica", key="pw-goto-dispatch", type="primary"):
                _go_to_page("⑤ Pubblica")


def _render_dispatch_page(settings_db_path: Path) -> None:
    col_platform, col_limit = st.columns([2, 1])
    with col_platform:
        platform_value = st.selectbox(
            "Social",
            options=["tutti", Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
            index=0,
            key="dispatch-platform",
        )
    with col_limit:
        limit = int(
            st.selectbox(
                "Max eventi",
                options=[20, 50, 100, 200],
                index=1,
                key="dispatch-limit",
            )
        )
    platform = None if platform_value == "tutti" else Platform(platform_value)
    dispatch_settings = load_settings()
    due_rows = list_due_events(
        settings_db_path,
        due_before=now_app(dispatch_settings),
        platform=platform,
        limit=limit,
    )
    due_story = collect_due_story_rules(
        settings_db_path,
        now=datetime.now(UTC),
        platform=platform,
        limit=limit,
    )
    if not due_rows:
        st.info("Nessun evento scaduto da pubblicare in questo momento (post pianificati).")
    else:
        st.caption(f"Eventi pronti al dispatch: {len(due_rows)}")
        settings = dispatch_settings
        enriched = []
        for row in due_rows:
            ok, reason = check_image_dispatch_gates(row, settings)
            enriched.append({**row, "dispatch_gate": "OK" if ok else reason})
        st.dataframe(enriched, width="stretch", hide_index=True)
    st.caption(f"Regole story dovute ora: {len(due_story)}")
    if due_story:
        rows_show = []
        for r in due_story:
            plat = r.get("platform")
            pv = plat.value if isinstance(plat, Platform) else str(plat)
            rows_show.append({**r, "platform": pv})
        st.dataframe(rows_show, width="stretch", hide_index=True)
    run_col, dry_col = st.columns(2)
    if run_col.button("Esegui dispatch ora", type="primary"):
        cmd = [sys.executable, "-m", "social_automation", "dispatch-scheduled", "--limit", str(limit)]
        if platform is not None:
            cmd.extend(["--platform", platform.value])
        proc = subprocess.run(
            cmd,
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            st.success("Dispatch completato.")
        else:
            st.error("Dispatch completato con errori.")
        if proc.stdout.strip():
            st.code(proc.stdout.strip())
        if proc.stderr.strip():
            st.code(proc.stderr.strip())
        st.rerun()
    if dry_col.button("Anteprima dispatch (dry-run)"):
        cmd = [
            sys.executable,
            "-m",
            "social_automation",
            "dispatch-scheduled",
            "--limit",
            str(limit),
            "--dry-run",
        ]
        if platform is not None:
            cmd.extend(["--platform", platform.value])
        proc = subprocess.run(
            cmd,
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.stdout.strip():
            st.code(proc.stdout.strip())
        if proc.stderr.strip():
            st.code(proc.stderr.strip())


def _run_rerender_for_planned_image(
    *,
    settings: Any,
    image_id: int,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
) -> dict[str, Any]:
    md = latest_metadata_for_image(settings.db_path, image_id=image_id)
    if md is None:
        raise RuntimeError("Metadati non trovati per l'immagine selezionata.")
    source_asset_id = str(md.get("source_asset_id", "") or "").strip()
    if not source_asset_id:
        raise RuntimeError(
            "Impossibile rerenderizzare: source_asset_id assente nei metadati."
        )
    source_asset_name = str(md.get("source_asset_name", "") or "").strip()
    business_category = str(md.get("business_category", "") or "").strip().lower()
    if not business_category:
        raise RuntimeError(
            "Impossibile rerenderizzare: business_category assente nei metadati."
        )

    canva_config = settings.canva_config_path
    if not canva_config.exists():
        raise RuntimeError(f"Config Canva non trovata: {canva_config}")

    canva_cfg = load_canva_yaml(canva_config)
    template_id = resolve_template_id(
        canva_cfg,
        platform=platform.value,
        category=business_category,
        media_format=media_format,
    )
    if not template_id:
        raise RuntimeError(
            f"Nessun template Canva per platform={platform.value} "
            f"category={business_category} format={media_format.value}."
        )

    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive_client = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=True,
        oauth_browser=oauth_browser,
    )
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = output_dir / f"drive_{source_asset_id}.jpg"
    source_path.write_bytes(drive_client.download_file_bytes(source_asset_id))

    canva_client = CanvaClient.from_token_file(
        settings.canva_client_id.strip(),
        settings.canva_client_secret.strip(),
        settings.canva_redirect_uri.strip(),
        settings.canva_token_path,
    )
    rendered = canva_client.render_for_platform(
        source_path,
        platform,
        template_id=template_id,
        output_dir=output_dir / "canva-rendered",
        output_stem=f"{business_category}_{source_asset_id}",
        use_placeholder=False,
        precrop_cover=True,
        media_format=media_format,
    )
    render_metadata = canva_client.get_last_render_metadata() or {}
    db_image_id = record_render_artifacts(
        settings.db_path,
        image_name=source_asset_name or rendered.name,
        image_path=rendered,
        source_asset_id=source_asset_id,
        source_asset_name=source_asset_name or None,
        business_category=business_category,
        metadata_payload=render_metadata,
    )
    return {
        "rendered_file": str(rendered),
        "db_image_id": str(db_image_id),
        "business_category": business_category,
        "platform": platform.value,
        "media_format": media_format.value,
        "template_id": template_id,
        "source_asset_id": source_asset_id,
        "source_asset_name": source_asset_name,
    }


def _render_manual_publication_approval_page(settings_db_path: Path) -> None:
    st.caption(
        "Controlla il ritocco foto. Solo le immagini **approvate** compaiono in **④ Pianifica**."
    )
    require_quality = False

    col_social, col_format, col_cat = st.columns([2, 2, 2])
    with col_social:
        platform = Platform(
            st.selectbox(
                "Social",
                options=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
                key="approve-platform",
            )
        )
    with col_format:
        plan_format = MediaFormat(
            st.selectbox(
                "Formato",
                options=[MediaFormat.POST.value, MediaFormat.STORY.value],
                format_func=_media_format_label,
                key="approve-format",
            )
        )
    with col_cat:
        category_options = ["tutte"] + _business_category_options(_DEFAULT_CATEGORIES_CONFIG)
        selected_category = st.selectbox(
            "Categoria business",
            options=category_options,
            index=0,
            key="approve-category",
        )

    category_filter = None if selected_category == "tutte" else selected_category
    filter_key = f"{platform.value}|{plan_format.value}|{selected_category}"
    if st.session_state.get("approve-filter-key") != filter_key:
        st.session_state["approve-filter-key"] = filter_key
        st.session_state["approve-page-index"] = 0

    total = count_images_for_manual_publication_review(
        settings_db_path,
        platform=platform,
        business_category=category_filter,
        media_format=plan_format,
        require_quality_pass=require_quality,
        pending_manual_only=True,
        require_ai_output=False,
    )
    if total == 0:
        st.info(
            "Nessuna immagine in attesa di approvazione. "
            "Elabora nuove foto in **① Seleziona** → **② Output AI**."
        )
        _render_workflow_footer(3)
        return

    max_page = max(0, (total - 1) // _APPROVAL_PAGE_SIZE)
    page_index = max(0, int(st.session_state.get("approve-page-index", 0)))
    if page_index > max_page:
        page_index = max_page
        st.session_state["approve-page-index"] = page_index

    nav_a, nav_b, nav_info, _ = st.columns([1, 1, 4, 2])
    with nav_a:
        if st.button("◀", disabled=page_index <= 0, key="approve-page-prev"):
            st.session_state["approve-page-index"] = max(0, page_index - 1)
            st.rerun()
    with nav_b:
        if st.button("▶", disabled=page_index >= max_page, key="approve-page-next"):
            st.session_state["approve-page-index"] = min(max_page, page_index + 1)
            st.rerun()
    with nav_info:
        st.caption(
            f"Pagina {page_index + 1} di {max_page + 1} · {total} da approvare"
        )

    rows = list_images_for_manual_publication_review(
        settings_db_path,
        platform=platform,
        business_category=category_filter,
        media_format=plan_format,
        require_quality_pass=require_quality,
        pending_manual_only=True,
        require_ai_output=False,
        limit=_APPROVAL_PAGE_SIZE,
        offset=page_index * _APPROVAL_PAGE_SIZE,
    )

    for row in rows:
        image_id = int(row["id"])
        image_name = str(row.get("name", "")).strip() or f"Immagine {image_id}"
        image_path = Path(str(row.get("path", "")))
        manual = row.get("is_valid_for_publication")
        meta = latest_metadata_for_image(settings_db_path, image_id=image_id)
        source_file = str((meta or {}).get("source_file") or "")

        with st.container(border=True):
            st.markdown(f"**#{image_id}** · `{image_path.name}`")
            _render_before_after_row(
                source_path=source_file or str(row.get("original_path") or ""),
                processed_path=image_path,
                visual_score=float(row["visual_score"])
                if row.get("visual_score") is not None
                else None,
                visual_status=str(row.get("visual_status") or "") or None,
                editing_required=row.get("editing_required"),
            )
            method_hint = ""
            mj_raw = meta.get("metadata_json") if meta else None
            if mj_raw:
                try:
                    mj = json.loads(mj_raw) if isinstance(mj_raw, str) else mj_raw
                    if isinstance(mj, dict):
                        method_hint = str(mj.get("visual_method") or "").strip()
                except ValueError:
                    pass
            if method_hint:
                st.caption(f"Metodo elaborazione: `{method_hint}`")
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button(
                    "Approva ritocco",
                    key=f"approve-yes-{page_index}-{image_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    set_image_manual_publication_valid(
                        settings_db_path, image_id=image_id, value=1
                    )
                    st.rerun()
            with b2:
                if st.button(
                    "Usa originale",
                    key=f"approve-original-{page_index}-{image_id}",
                    use_container_width=True,
                    help="Scarta il ritocco AI e approva la foto originale (solo crop formato)",
                ):
                    try:
                        revert_image_to_original(
                            image_id,
                            settings=load_settings(),
                            approve=True,
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with b3:
                if st.button(
                    "Rifiuta",
                    key=f"approve-no-{page_index}-{image_id}",
                    use_container_width=True,
                ):
                    set_image_manual_publication_valid(
                        settings_db_path, image_id=image_id, value=0
                    )
                    st.rerun()

    _render_workflow_footer(3)


def _render_plan_image_page(settings_db_path: Path) -> None:
    render_plan_image_page(
        settings_db_path,
        business_category_options=_business_category_options(_DEFAULT_CATEGORIES_CONFIG),
        media_format_label=_media_format_label,
        weekday_it=_WEEKDAY_IT,
        plan_preview_dialog=_plan_step1_image_preview_dialog,
        render_copy_pack_preview=_render_copy_pack_preview,
        render_workflow_footer=_render_workflow_footer,
        load_schedule_yaml=load_schedule_yaml,
        resolve_schedule_path=resolve_schedule_path,
    )



def _render_publish_page(settings_db_path: Path) -> None:
    tab_dispatch, tab_cal = st.tabs(["Pubblica ora", "Calendario"])
    with tab_dispatch:
        _render_dispatch_page(settings_db_path)
    with tab_cal:
        _render_planning_calendar(settings_db_path)
    _render_workflow_footer(5)


def _render_automation_page(settings_db_path: Path) -> None:
    tab_pw, tab_batch = st.tabs(["Prepara settimana", "Monitor batch"])
    with tab_pw:
        _render_prepare_week_page(settings_db_path)
    with tab_batch:
        _render_batch_dashboard(settings_db_path)


def _render_select_drive_page(settings: Any) -> None:
    st.caption(
        "Carica le foto da Drive (stesso elenco di sempre), seleziona quelle da passare "
        "a Story AI e avvia la coda."
    )
    col_a, col_c, col_d = st.columns([2, 1, 1])
    with col_a:
        category_options = _business_category_options(_DEFAULT_CATEGORIES_CONFIG)
        if st.session_state.get("render-category") not in category_options:
            st.session_state["render-category"] = (
                "food" if "food" in category_options else category_options[0]
            )
        category = st.selectbox(
            "Categoria",
            options=category_options,
            key="render-category",
        )
    today = today_app(load_settings())
    with col_c:
        target_year = int(
            st.number_input(
                "Anno",
                min_value=2000,
                max_value=2100,
                value=int(today.year),
                key="render-target-year",
            )
        )
    with col_d:
        target_month = int(
            st.selectbox(
                "Mese",
                options=list(range(1, 13)),
                index=max(0, int(today.month) - 1),
                format_func=lambda m: f"{m:02d} · {_MONTH_NAME_IT[int(m)]}",
                key="render-target-month",
            )
        )

    if st.button("Carica immagini da Drive", type="secondary", key="drive-load-btn"):
        try:
            _clear_legacy_drive_cache(settings)
            _clear_drive_thumb_cache(settings)
            assets = _load_drive_assets_for_selection(
                settings,
                category=category.strip(),
                target_year=target_year,
                target_month=target_month,
            )
            st.session_state["drive-asset-list"] = [
                {
                    "file_id": a.file_id,
                    "name": a.name,
                    "mime_type": a.mime_type,
                    "category": a.category,
                    "path_segments": a.path_segments,
                }
                for a in assets
            ]
            st.session_state["drive-selected-ids"] = []
            st.session_state["drive-select-page-index"] = 0
            st.success(f"Caricate {len(assets)} immagini da Drive.")
        except Exception as exc:
            st.error(str(exc))
            st.exception(exc)

    assets_data: list[dict[str, Any]] = list(
        st.session_state.get("drive-asset-list") or []
    )
    if not assets_data:
        st.info("Imposta filtri e clicca **Carica immagini da Drive**.")
        return

    selected_ids: list[str] = [
        str(x) for x in st.session_state.get("drive-selected-ids", []) if str(x)
    ]
    total = len(assets_data)
    max_page = max(0, (total - 1) // _DRIVE_SELECT_PAGE_SIZE)
    page_index = max(0, int(st.session_state.get("drive-select-page-index", 0)))
    if page_index > max_page:
        page_index = max_page
        st.session_state["drive-select-page-index"] = page_index

    nav_prev, nav_next, nav_info, _ = st.columns([1, 1, 4, 2])
    with nav_prev:
        if st.button("◀", disabled=page_index <= 0, key="drive-select-prev"):
            st.session_state["drive-select-page-index"] = max(0, page_index - 1)
            st.rerun()
    with nav_next:
        if st.button("▶", disabled=page_index >= max_page, key="drive-select-next"):
            st.session_state["drive-select-page-index"] = min(max_page, page_index + 1)
            st.rerun()
    with nav_info:
        st.caption(
            f"Pagina {page_index + 1} di {max_page + 1} · {total} immagini · "
            f"{len(selected_ids)} selezionate"
        )

    page_start = page_index * _DRIVE_SELECT_PAGE_SIZE
    page_assets = assets_data[page_start : page_start + _DRIVE_SELECT_PAGE_SIZE]
    page_ids = {str(a["file_id"]) for a in page_assets}

    def _clear_drive_pick_keys() -> None:
        for kk in list(st.session_state.keys()):
            if isinstance(kk, str) and kk.startswith("drive-pick-"):
                del st.session_state[kk]

    c_all, c_clear = st.columns(2)
    with c_all:
        if st.button(
            f"Seleziona tutte ({total})",
            key="drive-select-all",
        ):
            st.session_state["drive-selected-ids"] = [
                str(a["file_id"]) for a in assets_data
            ]
            _clear_drive_pick_keys()
            st.rerun()
    with c_clear:
        if st.button("Deseleziona tutte", key="drive-select-clear"):
            st.session_state["drive-selected-ids"] = []
            _clear_drive_pick_keys()
            st.rerun()

    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive_client = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=True,
        oauth_browser=oauth_browser,
    )

    cols = st.columns(5)
    merged_other = [fid for fid in selected_ids if fid not in page_ids]
    page_picked: list[str] = []
    for i, asset_dict in enumerate(page_assets):
        fid = str(asset_dict["file_id"])
        name = str(asset_dict.get("name") or fid)
        mime = str(asset_dict.get("mime_type") or "image/jpeg")
        pick_key = f"drive-pick-{page_index}-{fid}"
        if pick_key not in st.session_state:
            st.session_state[pick_key] = fid in selected_ids
        with cols[i % 5]:
            thumb = _get_drive_thumb(
                settings,
                drive_client,
                file_id=fid,
                mime_type=mime,
            )
            if thumb and thumb.is_file():
                st.image(str(thumb), caption=name[:40], width="stretch")
            else:
                st.caption(f"{name} (anteprima non disponibile)")
            if st.checkbox("Seleziona", key=pick_key):
                page_picked.append(fid)

    st.session_state["drive-selected-ids"] = merged_other + page_picked
    selected_ids = list(st.session_state["drive-selected-ids"])

    col_p, col_f = st.columns(2)
    with col_p:
        platform_value = st.selectbox(
            "Social destinazione (export/crop)",
            options=[Platform.INSTAGRAM.value, Platform.FACEBOOK.value],
            key="render-platform",
        )
    with col_f:
        format_value = st.selectbox(
            "Formato export",
            options=[MediaFormat.POST.value, MediaFormat.STORY.value],
            format_func=_media_format_label,
            key="render-format",
        )

    st.caption(
        f"Selezionate: **{len(selected_ids)}** foto · la coda esegue **solo ritocco/miglioramento**."
    )
    if st.button(
        "Avvia coda ritocco foto",
        type="primary",
        disabled=len(selected_ids) == 0,
        key="start-ai-queue",
    ):
        try:
            selected_platform = Platform(platform_value)
            selected_format = MediaFormat(format_value)
            aliases = (
                load_category_aliases(_DEFAULT_CATEGORIES_CONFIG)
                if _DEFAULT_CATEGORIES_CONFIG.exists()
                else {}
            )
            business_category = normalize_business_category(category.strip(), aliases)
            chosen_assets = [
                a for a in assets_data if str(a["file_id"]) in set(selected_ids)
            ]
            queue_dir = settings.output_dir / "batch_queues"
            queue_dir.mkdir(parents=True, exist_ok=True)
            batch_id = create_batch(
                settings.db_path,
                category=category.strip(),
                platform=selected_platform,
                requested_count=len(chosen_assets),
                media_format=selected_format,
                note="selected-drive-ai",
            )
            queue_file = queue_dir / f"{batch_id}.json"
            queue_file.write_text(
                json.dumps(
                    {
                        "platform": selected_platform.value,
                        "media_format": selected_format.value,
                        "category": category.strip(),
                        "business_category": business_category,
                        "assets": chosen_assets,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            runner_pid = _launch_selected_ai_batch_job(
                batch_id=batch_id,
                queue_file=queue_file,
            )
            mark_batch_runner_pid(
                settings.db_path,
                batch_id=batch_id,
                runner_pid=runner_pid,
            )
            st.session_state["render-active-batch-id"] = int(batch_id)
            st.success(
                f"Coda ritocco avviata: batch #{batch_id}, {len(chosen_assets)} foto."
            )
            _go_to_page("② Output AI")
        except Exception as exc:
            st.error(str(exc))
            st.exception(exc)


def _render_ai_output_page(settings: Any) -> None:
    st.caption("Anteprima ritocco: originale Drive vs asset finale (il copy si genera in **④ Pianifica**).")
    filt = st.selectbox(
        "Filtro",
        options=["pending", "approved", "rejected", "all"],
        format_func=lambda x: {
            "pending": "Da approvare",
            "approved": "Approvate",
            "rejected": "Rifiutate",
            "all": "Tutte",
        }.get(x, x),
        key="ai-output-filter",
    )
    rows = list_ai_output_images(
        settings.db_path,
        approval_filter=filt,
        limit=24,
    )
    if not rows:
        st.info("Nessun output AI. Vai a **① Seleziona** e avvia una coda.")
    else:
        st.caption(f"Mostrate {len(rows)} immagini (max 24).")
        for row in rows:
            image_id = int(row["id"])
            processed = Path(str(row.get("path") or ""))
            with st.container(border=True):
                st.markdown(f"**#{image_id}** · `{processed.name}`")
                _render_before_after_row(
                    source_path=str(row.get("source_file") or row.get("original_path") or ""),
                    processed_path=processed,
                    visual_score=float(row["visual_score"])
                    if row.get("visual_score") is not None
                    else None,
                    visual_status=str(row.get("visual_status") or "") or None,
                    editing_required=row.get("editing_required"),
                )
                manual = row.get("is_valid_for_publication")
                if manual is None:
                    st.warning("In attesa di approvazione")
                elif int(manual) == 1:
                    st.success("Approvata")
                else:
                    st.error("Rifiutata")

    current_batch_id = st.session_state.get("render-active-batch-id")
    if isinstance(current_batch_id, int):
        st.divider()
        st.markdown("#### Coda in esecuzione")
        _maybe_toast_batch_status(settings.db_path, current_batch_id)
        _render_batch_live_status(settings.db_path, current_batch_id)
        if st.button("Aggiorna stato coda", key="ai-output-refresh-batch"):
            st.rerun()
        batch_row = get_batch(settings.db_path, batch_id=current_batch_id)
        if batch_row and str(batch_row.get("status", "")).lower() in {
            "completed",
            "partial",
        }:
            if st.button("Vai ad Approva →", key="output-goto-approve", type="primary"):
                _go_to_page("③ Approva")


def main() -> None:
    st.set_page_config(
        page_title="Story Social",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _ensure_ui_state_defaults()
    settings = load_settings()

    st.title("Story Social")
    st.caption("Drive → ritocco AI → approvazione → pianificazione → Meta")

    menu_col, content_col = st.columns([2, 7])
    with menu_col:
        st.markdown("### Percorso")
        current = _current_ui_page()
        page = st.radio(
            "Menu",
            options=_UI_PAGES,
            index=_UI_PAGES.index(current),
            label_visibility="collapsed",
        )
        if page != current:
            st.session_state["ui-page"] = page
            st.rerun()
        st.session_state["ui-page"] = page
        st.divider()
        stats = _workflow_stats(settings.db_path, settings)
        st.markdown("**In sintesi**")
        st.markdown(f"- Da approvare: **{stats['pending_approval']}**")
        st.markdown(f"- Da pianificare: **{stats['ready_to_plan']}**")
        st.markdown(f"- Da pubblicare: **{stats['due_dispatch']}**")
        if stats["running_batches"]:
            st.markdown(f"- Batch attivi: **{stats['running_batches']}**")

    with content_col:
        if page == "Home":
            _render_home_page(settings.db_path, settings)
        elif page == "① Seleziona":
            _render_workflow_step_header(1, "Seleziona da Drive")
            _render_select_drive_page(settings)
            _render_workflow_footer(1)
        elif page == "② Output AI":
            _render_workflow_step_header(2, "Output ritocco")
            _render_ai_output_page(settings)
            _render_workflow_footer(2)
        elif page == "③ Approva":
            _render_workflow_step_header(3, "Approva foto")
            _render_manual_publication_approval_page(settings.db_path)
        elif page == "④ Pianifica":
            _render_workflow_step_header(4, "Pianifica")
            _render_plan_image_page(settings.db_path)
        elif page == "⑤ Pubblica":
            _render_workflow_step_header(5, "Pubblica")
            _render_publish_page(settings.db_path)
        elif page == "Automazione":
            st.subheader("Automazione")
            st.caption("Prepara l'intera settimana o monitora i batch in background.")
            _render_automation_page(settings.db_path)


if __name__ == "__main__":
    main()

