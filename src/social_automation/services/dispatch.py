"""Servizio dispatch eventi pianificati e regole story."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from social_automation.app_timezone import now_app
from social_automation.db.store import list_due_events
from social_automation.meta.client import MetaClient
from social_automation.models import Platform
from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.scheduling.dispatch_runner import DispatchRunResult, run_dispatch_scheduled
from social_automation.scheduling.story_rules_dispatch import collect_due_story_rules
from social_automation.settings import Settings, load_settings


def _serialize_due_event(row: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    ok, reason = check_image_dispatch_gates(row, settings)
    return {
        "id": int(row["id"]),
        "image_id": int(row["image_id"]),
        "image_name": str(row.get("image_name") or ""),
        "platform": str(row.get("platform") or ""),
        "event_type": str(row.get("event_type") or ""),
        "scheduled_for": str(row.get("scheduled_for") or ""),
        "external_id": row.get("external_id"),
        "detail": row.get("detail"),
        "dispatch_gate": "OK" if ok else reason,
    }


def _serialize_story_rule(row: dict[str, Any]) -> dict[str, Any]:
    plat = row.get("platform")
    platform_value = plat.value if isinstance(plat, Platform) else str(plat)
    return {
        "rule_id": int(row["rule_id"]),
        "image_id": int(row["image_id"]),
        "platform": platform_value,
        "schedule_mode": str(row.get("schedule_mode") or ""),
        "occurrence_key": str(row.get("occurrence_key") or ""),
        "slot_label": str(row.get("slot_label") or ""),
        "scheduled_for": str(row.get("scheduled_for") or ""),
        "image_path": str(row.get("image_path") or ""),
        "caption": str(row.get("caption") or ""),
    }


def list_due(
    db_path,
    *,
    platform: Platform | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or load_settings()
    due_rows = list_due_events(
        db_path,
        due_before=now_app(s),
        platform=platform,
        limit=max(1, int(limit)),
    )
    due_story = collect_due_story_rules(
        db_path,
        now=datetime.now(UTC),
        platform=platform,
        limit=max(1, int(limit)),
    )
    return {
        "planning_events": [_serialize_due_event(r, settings=s) for r in due_rows],
        "story_rules": [_serialize_story_rule(r) for r in due_story],
        "planning_count": len(due_rows),
        "story_count": len(due_story),
    }


def preview_dispatch(
    db_path,
    *,
    platform: Platform | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    data = list_due(db_path, platform=platform, limit=limit, settings=settings)
    return {
        **data,
        "dry_run": True,
        "message": (
            f"Anteprima: {data['planning_count']} eventi post, "
            f"{data['story_count']} regole story."
        ),
    }


def _serialize_run_result(result: DispatchRunResult) -> dict[str, Any]:
    return {
        "planning_published": result.planning_published,
        "planning_failed": result.planning_failed,
        "planning_skipped": result.planning_skipped,
        "story_published": result.story_published,
        "story_failed": result.story_failed,
        "story_skipped_reserve": result.story_skipped_reserve,
        "skip_reasons": list(result.skip_reasons),
    }


def run_dispatch(
    db_path,
    *,
    platform: Platform | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or load_settings()
    preview = list_due(db_path, platform=platform, limit=limit, settings=s)
    if preview["planning_count"] == 0 and preview["story_count"] == 0:
        return {
            "dry_run": False,
            "message": "Nessun evento scaduto da pubblicare.",
            **_serialize_run_result(DispatchRunResult()),
        }
    if not s.meta_page_access_token.strip():
        raise ValueError("META_PAGE_ACCESS_TOKEN mancante nel .env.")
    meta = MetaClient(
        s.meta_page_access_token.strip(),
        s.meta_ig_user_id.strip(),
        graph_version=(s.meta_graph_version or "v22.0").strip(),
        settings=s,
    )
    result = run_dispatch_scheduled(
        s,
        meta,
        platform=platform,
        limit=max(1, int(limit)),
    )
    serialized = _serialize_run_result(result)
    failed = result.planning_failed + result.story_failed
    msg = (
        f"Dispatch completato: pubblicati={result.planning_published + result.story_published}, "
        f"falliti={failed}, saltati={result.planning_skipped + result.story_skipped_reserve}."
    )
    if failed > 0:
        msg += " Alcuni eventi sono falliti."
    return {"dry_run": False, "message": msg, **serialized}
