"""Servizio automazione (prepara settimana)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from social_automation.config_loaders import resolve_schedule_path
from social_automation.scheduling.prepare_week import PrepareWeekResult, prepare_week
from social_automation.settings import Settings, load_settings


def _serialize_prepare_week_result(result: PrepareWeekResult) -> dict[str, Any]:
    return {
        "planned": result.planned,
        "processed": result.processed,
        "rendered": result.rendered,
        "skipped_occupied": result.skipped_occupied,
        "skipped_quality": result.skipped_quality,
        "skipped_borderline": result.skipped_borderline,
        "skipped_no_asset": result.skipped_no_asset,
        "auto_approved": result.auto_approved,
        "vision_evaluated": result.vision_evaluated,
        "errors": list(result.errors),
        "assignments": list(result.assignments),
    }


def run_prepare_week(
    *,
    days: int = 7,
    dry_run: bool = True,
    try_render: bool = True,
    schedule_path: Path | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or load_settings()
    sched_path = resolve_schedule_path(schedule_path or s.schedule_config_path)
    if not sched_path.is_file():
        raise FileNotFoundError(
            "Calendario editoriale non trovato. Copia config/schedule.example.yaml "
            "in config/schedule.yaml."
        )
    effective_render = try_render and not dry_run
    result = prepare_week(
        schedule_path=sched_path,
        settings=s,
        days=max(1, int(days)),
        dry_run=bool(dry_run),
        try_render=effective_render,
    )
    body = _serialize_prepare_week_result(result)
    body["schedule_path"] = str(sched_path)
    body["dry_run"] = dry_run
    body["message"] = (
        f"Completato: pianificati={result.planned}, render={result.rendered}, "
        f"auto-approvati={result.auto_approved}, vision={result.vision_evaluated}"
    )
    return body
