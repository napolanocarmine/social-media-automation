from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from social_automation.config_loaders import load_schedule_yaml
from social_automation.db.store import add_planning_event, ensure_db_schema, record_render_artifacts
from social_automation.models import Platform
from social_automation.scheduling.slot_planner import (
    iter_schedule_slots,
    list_free_schedule_slots,
    suggest_next_free_slot,
)


def test_iter_schedule_slots_monday(tmp_path: Path) -> None:
    sched = load_schedule_yaml(Path("config/schedule.example.yaml"))
    start = datetime(2026, 6, 22, 0, 0, tzinfo=UTC)  # Monday
    end = start + timedelta(days=7)
    slots = iter_schedule_slots(sched, start=start, end=end)
    assert any(s.platform == Platform.INSTAGRAM and s.weekday == "monday" for s in slots)


def test_suggest_skips_occupied_slot(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    img = tmp_path / "p.jpg"
    img.write_bytes(b"x")
    image_id = record_render_artifacts(
        db_path,
        image_name="p",
        image_path=img,
        metadata_payload={"platform": "instagram"},
    )
    sched = load_schedule_yaml(Path("config/schedule.example.yaml"))
    tz = ZoneInfo(sched.timezone)
    # Next Monday 12:30 Europe/Rome from 2026-06-22
    monday_local = datetime(2026, 6, 22, 12, 30, tzinfo=tz)
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        event_type="planned",
        scheduled_for=monday_local.astimezone(UTC),
    )
    after = datetime(2026, 6, 22, 8, 0, tzinfo=UTC)
    free = list_free_schedule_slots(db_path, sched, start=after, end=after + timedelta(days=7))
    monday_ig = [
        s
        for s in free
        if s.platform == Platform.INSTAGRAM and s.weekday == "monday" and s.time_hhmm == "12:30"
    ]
    assert monday_ig == []
    nxt = suggest_next_free_slot(db_path, sched, platform=Platform.INSTAGRAM, after=after)
    assert nxt is not None
    assert not (nxt.weekday == "monday" and nxt.time_hhmm == "12:30")
