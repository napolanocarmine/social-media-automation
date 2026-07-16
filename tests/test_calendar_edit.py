from __future__ import annotations

from datetime import datetime
from pathlib import Path

from social_automation.brand.copy_pack import caption_from_planning_detail, planning_detail_with_caption
from social_automation.db.store import (
    add_planning_event,
    ensure_db_schema,
    latest_plan_for_image,
    list_calendar_items,
    list_pending_events,
    record_render_artifacts,
)
from social_automation.models import Platform
from social_automation.web.calendar_edit_ui import _save_cancel, _save_reschedule


def test_caption_from_planning_detail_json() -> None:
    detail = planning_detail_with_caption("Ciao mondo")
    assert caption_from_planning_detail(detail) == "Ciao mondo"


def test_save_reschedule_creates_rescheduled_event(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    img = tmp_path / "post.jpg"
    img.write_bytes(b"x")
    image_id = record_render_artifacts(
        db_path,
        image_name="post",
        image_path=img,
        metadata_payload={"platform": "instagram"},
    )
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        event_type="planned",
        scheduled_for=datetime(2026, 6, 20, 10, 0, 0),
        detail=planning_detail_with_caption("Prima caption"),
    )
    ev = list_pending_events(db_path, limit=10)[0]
    msg = _save_reschedule(
        db_path,
        ev=ev,
        plan_date=datetime(2026, 6, 25).date(),
        plan_time=datetime(2026, 6, 25, 15, 30).time(),
        caption="Nuova caption",
        media_format=__import__("social_automation.models", fromlist=["MediaFormat"]).MediaFormat.POST,
    )
    assert "aggiornata" in msg.lower()
    latest = latest_plan_for_image(db_path, image_id=image_id, platform=Platform.INSTAGRAM)
    assert latest is not None
    assert latest["event_type"] == "rescheduled"
    assert "2026-06-25" in str(latest["scheduled_for"])
    assert caption_from_planning_detail(str(latest["detail"])) == "Nuova caption"


def test_save_cancel_removes_from_calendar(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    img = tmp_path / "story.jpg"
    img.write_bytes(b"x")
    image_id = record_render_artifacts(
        db_path,
        image_name="story",
        image_path=img,
        metadata_payload={"platform": "instagram"},
    )
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        event_type="planned",
        scheduled_for=datetime(2026, 7, 1, 9, 0, 0),
    )
    ev = list_pending_events(db_path, limit=10)[0]
    _save_cancel(db_path, ev=ev)
    assert list_pending_events(db_path, limit=10) == []
    ensure_db_schema(db_path)
    items = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 7, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 8, 1, 0, 0, 0),
        limit=10,
    )
    assert items == []
