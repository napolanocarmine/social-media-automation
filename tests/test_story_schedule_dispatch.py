"""Regole di pubblicazione story ricorrenti / one-shot."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from social_automation.db.store import (
    add_story_schedule_rule,
    ensure_db_schema,
    record_render_artifacts,
    reserve_story_occurrence_slot,
    story_occurrence_exists,
)
from social_automation.models import MediaFormat, Platform
from social_automation.scheduling.story_rules_dispatch import collect_due_story_rules


def test_collect_weekly_friday_after_slot(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    img = tmp_path / "s.jpg"
    img.write_bytes(b"x")
    record_render_artifacts(
        db_path,
        image_name="s",
        image_path=img,
        source_asset_id="a1",
        source_asset_name="n",
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "T",
            "media_format": MediaFormat.STORY.value,
        },
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT id FROM images LIMIT 1").fetchone()
    image_id = int(row[0])
    add_story_schedule_rule(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        schedule_mode="weekly",
        timezone_name="Europe/Rome",
        weekday=4,
        time_local="09:00",
        detail='{"caption": "ciao"}',
    )
    fri = datetime(2026, 5, 15, 10, 0, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)
    due = collect_due_story_rules(db_path, now=fri, limit=10)
    assert len(due) == 1
    assert due[0]["schedule_mode"] == "weekly"
    assert due[0]["caption"] == "ciao"

    thu = datetime(2026, 5, 14, 10, 0, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)
    assert collect_due_story_rules(db_path, now=thu, limit=10) == []

    fri_before = datetime(2026, 5, 15, 8, 0, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)
    assert collect_due_story_rules(db_path, now=fri_before, limit=10) == []


def test_collect_weekly_skips_if_occurrence_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    img = tmp_path / "s2.jpg"
    img.write_bytes(b"x")
    record_render_artifacts(
        db_path,
        image_name="s2",
        image_path=img,
        source_asset_id="a2",
        source_asset_name="n",
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "T",
            "media_format": MediaFormat.STORY.value,
        },
    )
    with sqlite3.connect(db_path) as conn:
        image_id = int(conn.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1").fetchone()[0])
    rid = add_story_schedule_rule(
        db_path,
        image_id=image_id,
        platform=Platform.FACEBOOK,
        schedule_mode="weekly",
        timezone_name="Europe/Rome",
        weekday=4,
        time_local="09:00",
    )
    dkey = "2026-05-15"
    assert reserve_story_occurrence_slot(db_path, rule_id=rid, occurrence_date=dkey)
    assert story_occurrence_exists(db_path, rule_id=rid, occurrence_date=dkey)
    fri = datetime(2026, 5, 15, 10, 0, 0, tzinfo=ZoneInfo("Europe/Rome")).astimezone(UTC)
    assert collect_due_story_rules(db_path, now=fri, limit=10) == []


def test_collect_once_past(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    img = tmp_path / "s3.jpg"
    img.write_bytes(b"x")
    record_render_artifacts(
        db_path,
        image_name="s3",
        image_path=img,
        source_asset_id="a3",
        source_asset_name="n",
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "T",
            "media_format": MediaFormat.STORY.value,
        },
    )
    with sqlite3.connect(db_path) as conn:
        image_id = int(conn.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1").fetchone()[0])
    when = datetime(2020, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Europe/Rome"))
    add_story_schedule_rule(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        schedule_mode="once",
        timezone_name="Europe/Rome",
        scheduled_for=when,
    )
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    due = collect_due_story_rules(db_path, now=now, limit=10)
    assert len(due) == 1
    assert due[0]["schedule_mode"] == "once"
