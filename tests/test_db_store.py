from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from social_automation.app_timezone import scheduled_for_db_iso
from social_automation.db.store import (
    add_batch_item,
    add_planning_event,
    count_images_for_manual_publication_review,
    count_plannable_images,
    create_batch,
    ensure_db_schema,
    finalize_batch,
    get_batch,
    get_batch_stop_message,
    get_images_by_ids,
    has_source_asset_render_for_platform,
    latest_metadata_for_image,
    latest_plan_for_image,
    list_batch_items,
    list_batches,
    list_calendar_items,
    list_due_events,
    list_images_for_manual_publication_review,
    list_pending_events,
    list_plannable_image_ids,
    list_plannable_images,
    record_render_artifacts,
    request_batch_stop,
    set_image_manual_publication_valid,
)
from social_automation.models import MediaFormat, Platform
from db_test_helpers import (
    execute_sql,
    fetchall_sql,
    fetchone_sql,
    metadata_json_payload,
    requires_sqlite,
    table_columns,
)


def test_record_render_artifacts_inserts_image_and_metadata(db_path: Path, tmp_path: Path) -> None:
    rendered = tmp_path / "out.jpg"
    rendered.write_bytes(b"img")
    metadata_path = tmp_path / "out.json"
    metadata_path.write_text(
        json.dumps(
            {
                "platform": "instagram",
                "template_id": "DAxxx",
                "canvas_width": 1080,
                "canvas_height": 1080,
                "mode": "connect_upload_create_export",
            }
        ),
        encoding="utf-8",
    )

    image_id = record_render_artifacts(
        db_path,
        image_name="my-image",
        image_path=rendered,
        source_asset_id="drive123",
        source_asset_name="drive name",
        business_category="food",
        metadata_payload=json.loads(metadata_path.read_text(encoding="utf-8")),
    )

    row = fetchone_sql(
        db_path,
        "SELECT name, path, render_ig, render_fb FROM images WHERE id = ?",
        (image_id,),
    )
    assert row == ("my-image", str(rendered), 1, 0)
    md = fetchone_sql(
        db_path,
        "SELECT platform, template_id, source_asset_id, business_category "
        "FROM metadata WHERE image_id = ?",
        (image_id,),
    )
    assert md == ("instagram", "DAxxx", "drive123", "food")
    assert has_source_asset_render_for_platform(
        db_path,
        source_asset_id="drive123",
        platform=Platform.INSTAGRAM,
    )
    plannable_ig = list_plannable_images(db_path, platform=Platform.INSTAGRAM, limit=10)
    assert plannable_ig and int(plannable_ig[0]["render_ig"]) == 1
    plannable_ig_food = list_plannable_images(
        db_path,
        platform=Platform.INSTAGRAM,
        business_category="food",
        limit=10,
    )
    assert plannable_ig_food
    plannable_ig_beer = list_plannable_images(
        db_path,
        platform=Platform.INSTAGRAM,
        business_category="beer",
        limit=10,
    )
    assert not plannable_ig_beer


def test_add_planning_event_inserts_history_row(db_path: Path, tmp_path: Path) -> None:
    rendered = tmp_path / "out.jpg"
    rendered.write_bytes(b"img")
    metadata_path = tmp_path / "out.json"
    metadata_path.write_text("{}", encoding="utf-8")
    image_id = record_render_artifacts(
        db_path,
        image_name="my-image",
        image_path=rendered,
        business_category="food",
        metadata_payload={},
    )

    planned = datetime(2026, 5, 8, 12, 0, 0)
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.FACEBOOK,
        event_type="planned",
        scheduled_for=planned,
        detail="test event",
    )
    row = fetchone_sql(
        db_path,
        "SELECT platform, event_type, scheduled_for, detail "
        "FROM planning_events WHERE image_id = ?",
        (image_id,),
    )
    assert row == (
        "facebook",
        "planned",
        scheduled_for_db_iso(planned),
        "test event",
    )
    latest = latest_plan_for_image(db_path, image_id=image_id, platform=Platform.FACEBOOK)
    assert latest is not None
    assert latest["event_type"] == "planned"
    pending = list_pending_events(db_path, platform=Platform.FACEBOOK, limit=10)
    assert pending and pending[0]["event_type"] == "planned"
    cal_items = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 5, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 6, 1, 0, 0, 0),
        limit=10,
    )
    assert cal_items and cal_items[0]["platform"] == "facebook"
    cal_fb = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 5, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 6, 1, 0, 0, 0),
        platform=Platform.FACEBOOK,
        limit=10,
    )
    assert cal_fb and cal_fb[0]["platform"] == "facebook"
    cal_ig = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 5, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 6, 1, 0, 0, 0),
        platform=Platform.INSTAGRAM,
        limit=10,
    )
    assert not cal_ig
    cal_food = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 5, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 6, 1, 0, 0, 0),
        business_category="food",
        limit=10,
    )
    assert cal_food
    cal_beer = list_calendar_items(
        db_path,
        start_inclusive=datetime(2026, 5, 1, 0, 0, 0),
        end_exclusive=datetime(2026, 6, 1, 0, 0, 0),
        business_category="beer",
        limit=10,
    )
    assert not cal_beer


def test_list_due_events_skips_planned_with_meta_external_id(db_path: Path, tmp_path: Path) -> None:
    """Se il post è già programmato su Meta (external_id), il dispatch non deve ripubblicare."""
    rendered = tmp_path / "out.jpg"
    rendered.write_bytes(b"img")
    image_id = record_render_artifacts(
        db_path,
        image_name="x",
        image_path=rendered,
        business_category="food",
        metadata_payload={},
    )
    past = datetime(2020, 1, 1, 12, 0, 0)
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.FACEBOOK,
        event_type="planned",
        scheduled_for=past,
        external_id="meta_post_123",
        detail="caption",
    )
    due = list_due_events(db_path, due_before=datetime(2026, 1, 1, 0, 0, 0), limit=50)
    assert due == []


def test_latest_metadata_for_image_returns_last_snapshot(db_path: Path, tmp_path: Path) -> None:
    rendered = tmp_path / "out.jpg"
    rendered.write_bytes(b"img")
    image_id = record_render_artifacts(
        db_path,
        image_name="img",
        image_path=rendered,
        source_asset_id="drive123",
        source_asset_name="image-a",
        business_category="food",
        metadata_payload={"platform": "instagram", "mode": "first"},
    )
    record_render_artifacts(
        db_path,
        image_name="img",
        image_path=rendered,
        source_asset_id="drive123",
        source_asset_name="image-a",
        business_category="food",
        metadata_payload={"platform": "instagram", "mode": "second"},
    )
    md = latest_metadata_for_image(db_path, image_id=image_id)
    assert md is not None
    assert md["source_asset_id"] == "drive123"
    assert md["business_category"] == "food"
    payload = metadata_json_payload(md)
    assert payload["mode"] == "second"


@requires_sqlite
def test_schema_migration_removes_redundant_planned_columns(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                render_ig INTEGER NOT NULL DEFAULT 0,
                render_fb INTEGER NOT NULL DEFAULT 0,
                planned_on_ig TEXT NULL,
                planned_on_fb TEXT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO images(name, path, planned_on_ig)
            VALUES ('old', '/tmp/x.jpg', '2026-05-08T12:00:00');
            """
        )
    ensure_db_schema(db_path)
    cols = table_columns(db_path, "images")
    assert "planned_on_ig" not in cols
    assert "planned_on_fb" not in cols
    row = fetchone_sql(db_path, "SELECT platform, event_type, scheduled_for FROM planning_events")
    assert row == ("instagram", "planned", "2026-05-08T12:00:00")


def test_batches_tables_store_status_items_and_errors(db_path: Path) -> None:
    ensure_db_schema(db_path)
    batch_id = create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=3,
    )
    add_batch_item(
        db_path,
        batch_id=batch_id,
        item_index=1,
        status="completed",
        source_asset_id="drive-1",
        source_asset_name="img-1",
        business_category="food",
        template_id="tpl-1",
        image_id=None,
        rendered_file="/tmp/a.jpg",
        payload={"platform": "instagram"},
    )
    add_batch_item(
        db_path,
        batch_id=batch_id,
        item_index=2,
        status="failed",
        error_message="Canva timeout",
        payload={"step": "export"},
    )
    finalize_batch(
        db_path,
        batch_id=batch_id,
        status="partial",
        completed_count=1,
        failed_count=1,
        last_error="Canva timeout",
    )
    batch_row = fetchone_sql(
        db_path,
        "SELECT status, category, platform, requested_count, completed_count, "
        "failed_count, last_error, finished_at FROM batches WHERE id = ?",
        (batch_id,),
    )
    assert batch_row is not None
    assert batch_row[0] == "partial"
    assert batch_row[1] == "food"
    assert batch_row[2] == "instagram"
    assert batch_row[3] == 3
    assert batch_row[4] == 1
    assert batch_row[5] == 1
    assert batch_row[6] == "Canva timeout"
    assert batch_row[7] is not None

    item_rows = fetchall_sql(
        db_path,
        "SELECT item_index, status, error_message FROM batch_items "
        "WHERE batch_id = ? ORDER BY item_index",
        (batch_id,),
    )
    assert len(item_rows) == 2
    assert item_rows[0] == (1, "completed", None)
    assert item_rows[1] == (2, "failed", "Canva timeout")
    batches = list_batches(db_path, status="partial", platform=Platform.INSTAGRAM, limit=10)
    assert batches and int(batches[0]["id"]) == batch_id
    items = list_batch_items(db_path, batch_id=batch_id, limit=10)
    assert len(items) == 2
    assert items[0]["status"] == "completed"
    assert items[1]["status"] == "failed"


def test_request_batch_stop_sets_manual_stop_message(db_path: Path) -> None:
    ensure_db_schema(db_path)
    batch_id = create_batch(
        db_path,
        category="beer",
        platform=Platform.INSTAGRAM,
        requested_count=2,
    )
    changed = request_batch_stop(
        db_path,
        batch_id=batch_id,
        reason="Stop per verifica contenuti Aprile 2026",
    )
    assert changed
    msg = get_batch_stop_message(db_path, batch_id=batch_id)
    assert msg is not None
    assert "Batch interrotto manualmente" in msg
    assert "Aprile 2026" in msg
    row = get_batch(db_path, batch_id=batch_id)
    assert row is not None
    assert row["status"] == "running"
    assert row["stop_requested_at"] is not None
    assert row["stop_reason"] == "Stop per verifica contenuti Aprile 2026"

    finalize_batch(
        db_path,
        batch_id=batch_id,
        status="cancelled",
        completed_count=0,
        failed_count=0,
        last_error=msg,
    )
    assert get_batch_stop_message(db_path, batch_id=batch_id) is None
    cancelled = list_batches(db_path, status="cancelled", platform=Platform.INSTAGRAM, limit=10)
    assert cancelled and int(cancelled[0]["id"]) == batch_id


def test_record_render_artifacts_tracks_story_separately_from_post(db_path: Path, tmp_path: Path) -> None:
    rendered_post = tmp_path / "post.jpg"
    rendered_post.write_bytes(b"img")
    rendered_story = tmp_path / "story.jpg"
    rendered_story.write_bytes(b"img")

    record_render_artifacts(
        db_path,
        image_name="post-image",
        image_path=rendered_post,
        source_asset_id="drive123",
        source_asset_name="drive name",
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "DAxxx",
            "media_format": MediaFormat.POST.value,
        },
    )
    record_render_artifacts(
        db_path,
        image_name="story-image",
        image_path=rendered_story,
        source_asset_id="drive123",
        source_asset_name="drive name",
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "DAStory",
            "media_format": MediaFormat.STORY.value,
        },
    )

    rows = fetchall_sql(
        db_path,
        "SELECT path, render_ig, render_fb, render_ig_story, render_fb_story "
        "FROM images ORDER BY id",
    )
    assert (str(rendered_post), 1, 0, 0, 0) in rows
    assert (str(rendered_story), 0, 0, 1, 0) in rows

    assert has_source_asset_render_for_platform(
        db_path,
        source_asset_id="drive123",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    )
    assert has_source_asset_render_for_platform(
        db_path,
        source_asset_id="drive123",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.STORY,
    )
    assert not has_source_asset_render_for_platform(
        db_path,
        source_asset_id="drive123",
        platform=Platform.FACEBOOK,
        media_format=MediaFormat.STORY,
    )

    plannable_post = list_plannable_images(
        db_path,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        limit=10,
    )
    plannable_story = list_plannable_images(
        db_path,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.STORY,
        limit=10,
    )
    plannable_story_fb = list_plannable_images(
        db_path,
        platform=Platform.FACEBOOK,
        media_format=MediaFormat.STORY,
        limit=10,
    )
    assert len(plannable_post) == 1
    assert plannable_post[0]["path"] == str(rendered_post)
    assert len(plannable_story) == 1
    assert plannable_story[0]["path"] == str(rendered_story)
    assert len(plannable_story_fb) == 1
    assert plannable_story_fb[0]["path"] == str(rendered_story)

    ids_story = list_plannable_image_ids(
        db_path,
        platform=Platform.FACEBOOK,
        media_format=MediaFormat.STORY,
    )
    assert ids_story == [int(plannable_story_fb[0]["id"])]
    by_ids = get_images_by_ids(db_path, ids_story)
    assert len(by_ids) == 1
    assert by_ids[0]["path"] == str(rendered_story)


def test_list_plannable_pagination_and_count(db_path: Path, tmp_path: Path) -> None:
    ensure_db_schema(db_path)
    for i in range(3):
        p = tmp_path / f"post_{i}.jpg"
        p.write_bytes(b"x")
        record_render_artifacts(
            db_path,
            image_name=f"img-{i}",
            image_path=p,
            source_asset_id=f"asset-{i}",
            source_asset_name=f"name-{i}",
            business_category="food",
            metadata_payload={
                "platform": Platform.INSTAGRAM.value,
                "template_id": "T",
                "media_format": MediaFormat.POST.value,
            },
        )
    assert count_plannable_images(
        db_path, platform=Platform.INSTAGRAM, media_format=MediaFormat.POST
    ) == 3
    ids = list_plannable_image_ids(db_path, platform=Platform.INSTAGRAM)
    assert len(ids) == 3
    page0 = list_plannable_images(db_path, platform=Platform.INSTAGRAM, limit=2, offset=0)
    page1 = list_plannable_images(db_path, platform=Platform.INSTAGRAM, limit=2, offset=2)
    assert len(page0) == 2
    assert len(page1) == 1
    assert {int(page0[0]["id"]), int(page0[1]["id"])} == set(ids[:2])
    assert int(page1[0]["id"]) == ids[2]


def test_plannable_respects_quality_gate_flag(db_path: Path, tmp_path: Path) -> None:
    """Quality gate e approvazione manuale: filtri ``list_plannable_*`` coerenti."""
    ensure_db_schema(db_path)
    ids: list[int] = []
    for i in range(3):
        p = tmp_path / f"qimg{i}.jpg"
        p.write_bytes(b"x")
        mid = record_render_artifacts(
            db_path,
            image_name=f"n{i}",
            image_path=p,
            business_category="food",
            metadata_payload={
                "platform": Platform.INSTAGRAM.value,
                "template_id": "T",
                "media_format": MediaFormat.POST.value,
            },
        )
        ids.append(mid)
    execute_sql(
        db_path,
        "UPDATE images SET is_valid_by_quality_evaluation = 1 WHERE id = ?",
        (ids[0],),
    )
    execute_sql(
        db_path,
        "UPDATE images SET is_valid_by_quality_evaluation = 0 WHERE id = ?",
        (ids[1],),
    )
    open_ids = list_plannable_image_ids(
        db_path, platform=Platform.INSTAGRAM, require_quality_pass=False
    )
    assert set(open_ids) == set(ids)

    gated = list_plannable_image_ids(
        db_path, platform=Platform.INSTAGRAM, require_quality_pass=True
    )
    assert gated == [ids[0]]

    ready = list_plannable_image_ids(
        db_path,
        platform=Platform.INSTAGRAM,
        require_quality_pass=True,
        require_manual_publication_valid=True,
    )
    assert ready == []

    set_image_manual_publication_valid(db_path, image_id=ids[0], value=1)
    ready2 = list_plannable_image_ids(
        db_path,
        platform=Platform.INSTAGRAM,
        require_quality_pass=True,
        require_manual_publication_valid=True,
    )
    assert ready2 == [ids[0]]

    rows = get_images_by_ids(db_path, [ids[0]])
    assert rows and rows[0].get("is_valid_by_quality_evaluation") in {1, True}
    assert rows[0].get("is_valid_for_publication") in {1, True}


def test_manual_publication_review_list_and_count(db_path: Path, tmp_path: Path) -> None:
    ensure_db_schema(db_path)
    p = tmp_path / "m.jpg"
    p.write_bytes(b"x")
    iid = record_render_artifacts(
        db_path,
        image_name="m",
        image_path=p,
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "T",
            "media_format": MediaFormat.POST.value,
        },
    )
    execute_sql(
        db_path,
        "UPDATE images SET is_valid_by_quality_evaluation = 1 WHERE id = ?",
        (iid,),
    )
    assert count_images_for_manual_publication_review(
        db_path, platform=Platform.INSTAGRAM, pending_manual_only=True, require_ai_output=False
    ) == 1
    rows = list_images_for_manual_publication_review(
        db_path,
        platform=Platform.INSTAGRAM,
        pending_manual_only=True,
        require_ai_output=False,
        limit=10,
    )
    assert len(rows) == 1 and int(rows[0]["id"]) == iid
    set_image_manual_publication_valid(db_path, image_id=iid, value=1)
    assert (
        count_images_for_manual_publication_review(
            db_path, platform=Platform.INSTAGRAM, pending_manual_only=True, require_ai_output=False
        )
        == 0
    )
    set_image_manual_publication_valid(db_path, image_id=iid, value=None)
    assert (
        count_images_for_manual_publication_review(
            db_path, platform=Platform.INSTAGRAM, pending_manual_only=True, require_ai_output=False
        )
        == 1
    )
    set_image_manual_publication_valid(db_path, image_id=iid, value=0)
    assert (
        count_images_for_manual_publication_review(
            db_path, platform=Platform.INSTAGRAM, pending_manual_only=True, require_ai_output=False
        )
        == 0
    )


def test_get_images_by_ids_includes_quality_prediction_fields(db_path: Path, tmp_path: Path) -> None:
    rendered = tmp_path / "q.jpg"
    rendered.write_bytes(b"x")
    image_id = record_render_artifacts(
        db_path,
        image_name="q",
        image_path=rendered,
        business_category="food",
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "template_id": "T",
            "media_format": MediaFormat.POST.value,
        },
    )
    execute_sql(
        db_path,
        """
        UPDATE images
        SET quality_predicted_class = ?,
            quality_predicted_confidence = ?
        WHERE id = ?
        """,
        ("good", 0.91, image_id),
    )
    rows = get_images_by_ids(db_path, [image_id])
    assert rows[0]["quality_predicted_class"] == "good"
    assert abs(float(rows[0]["quality_predicted_confidence"]) - 0.91) < 1e-9


def test_create_batch_records_media_format(db_path: Path) -> None:
    ensure_db_schema(db_path)
    post_batch = create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=1,
        media_format=MediaFormat.POST,
    )
    story_batch = create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=1,
        media_format=MediaFormat.STORY,
    )

    only_stories = list_batches(
        db_path,
        platform=Platform.INSTAGRAM,
        limit=10,
        media_format=MediaFormat.STORY,
    )
    assert [int(r["id"]) for r in only_stories] == [story_batch]

    only_posts = list_batches(
        db_path,
        platform=Platform.INSTAGRAM,
        limit=10,
        media_format=MediaFormat.POST,
    )
    assert [int(r["id"]) for r in only_posts] == [post_batch]

    add_batch_item(
        db_path,
        batch_id=story_batch,
        item_index=1,
        status="completed",
        business_category="food",
        media_format=MediaFormat.STORY,
        payload={"platform": Platform.INSTAGRAM.value},
    )
    items = list_batch_items(db_path, batch_id=story_batch, limit=10)
    assert items and items[0]["media_format"] == MediaFormat.STORY.value


def test_legacy_metadata_without_media_format_treated_as_post(db_path: Path, tmp_path: Path) -> None:
    """Compat: metadata senza media_format (NULL) conta come post."""
    rendered = tmp_path / "out.jpg"
    rendered.write_bytes(b"img")
    image_id = record_render_artifacts(
        db_path,
        image_name="legacy",
        image_path=rendered,
        source_asset_id="legacy123",
        business_category="food",
        metadata_payload={"platform": Platform.INSTAGRAM.value},
    )
    execute_sql(
        db_path,
        "UPDATE metadata SET media_format = NULL WHERE image_id = ?",
        (image_id,),
    )
    assert has_source_asset_render_for_platform(
        db_path,
        source_asset_id="legacy123",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    )
    assert not has_source_asset_render_for_platform(
        db_path,
        source_asset_id="legacy123",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.STORY,
    )
