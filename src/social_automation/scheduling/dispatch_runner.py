"""Esecuzione dispatch pianificati con gate di sicurezza."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from social_automation.app_timezone import now_app, parse_iso_datetime
from social_automation.db.store import add_planning_event, list_due_events
from social_automation.meta.client import MetaClient
from social_automation.models import MediaFormat, Platform, infer_media_format_from_render_path
from social_automation.brand.copy_pack import caption_for_platform
from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.scheduling.story_rules_dispatch import run_story_rules_dispatch
from social_automation.services.media import resolve_dispatch_image_path
from social_automation.settings import Settings


@dataclass
class DispatchRunResult:
    planning_published: int = 0
    planning_failed: int = 0
    planning_skipped: int = 0
    story_published: int = 0
    story_failed: int = 0
    story_skipped_reserve: int = 0
    skip_reasons: list[str] = field(default_factory=list)


def _caption_from_detail(detail: str) -> str:
    raw = (detail or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") and raw.endswith("}"):
        import json

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return str(payload.get("caption", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw


def _caption_for_dispatch(row: dict[str, Any], platform: Platform, media_format: MediaFormat) -> str:
    cap = _caption_from_detail(str(row.get("detail", "") or ""))
    if cap:
        return cap
    import json

    copy_raw = row.get("copy_json")
    if copy_raw:
        try:
            copy_data = json.loads(str(copy_raw))
            if isinstance(copy_data, dict):
                return caption_for_platform(copy_data, platform=platform, media_format=media_format)
        except json.JSONDecodeError:
            pass
    return ""


def _safe_scheduled_for(text: str, settings: Settings | None = None) -> datetime | None:
    return parse_iso_datetime(text, settings)


def run_dispatch_scheduled(
    settings: Settings,
    meta: MetaClient,
    *,
    platform: Platform | None = None,
    limit: int = 50,
    due_before: datetime | None = None,
) -> DispatchRunResult:
    """Pubblica eventi scaduti e regole story, rispettando i gate configurati."""
    result = DispatchRunResult()
    due_events = list_due_events(
        settings.db_path,
        due_before=due_before or now_app(settings),
        platform=platform,
        limit=max(1, int(limit)),
    )
    for row in due_events:
        image_id = int(row["image_id"])
        plat = Platform(str(row["platform"]))
        scheduled_for = _safe_scheduled_for(str(row.get("scheduled_for", "")), settings)
        ok, reason = check_image_dispatch_gates(row, settings)
        if not ok:
            result.planning_skipped += 1
            skip_detail = f"dispatch-skipped: {reason}"
            result.skip_reasons.append(f"image_id={image_id}\t{skip_detail}")
            add_planning_event(
                settings.db_path,
                image_id=image_id,
                platform=plat,
                event_type="skipped",
                scheduled_for=scheduled_for,
                detail=skip_detail,
            )
            continue

        image_path_raw = str(row.get("image_path", ""))
        mf = infer_media_format_from_render_path(Path(image_path_raw.split("/")[-1]))
        caption = _caption_for_dispatch(row, plat, mf)
        add_planning_event(
            settings.db_path,
            image_id=image_id,
            platform=plat,
            event_type="dispatched",
            scheduled_for=scheduled_for,
            detail="dispatch-scheduled",
        )
        try:
            image_path = resolve_dispatch_image_path(image_path_raw, settings=settings)
            mf_value = mf.value
            external_id = meta.publish_image(plat, image_path, caption, media_format=mf_value)
            add_planning_event(
                settings.db_path,
                image_id=image_id,
                platform=plat,
                event_type="published",
                scheduled_for=scheduled_for,
                external_id=str(external_id),
                detail="dispatch-scheduled",
            )
            result.planning_published += 1
        except Exception as exc:
            result.planning_failed += 1
            add_planning_event(
                settings.db_path,
                image_id=image_id,
                platform=plat,
                event_type="failed",
                scheduled_for=scheduled_for,
                detail=f"dispatch-scheduled: {exc}",
            )

    utc_now = datetime.now(UTC)
    sp_pub, sp_fail, sp_skip = run_story_rules_dispatch(
        settings.db_path,
        meta,
        now=utc_now,
        platform=platform,
        limit=limit,
        settings=settings,
    )
    result.story_published = sp_pub
    result.story_failed = sp_fail
    result.story_skipped_reserve = sp_skip
    return result
