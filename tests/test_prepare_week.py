from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from social_automation.db.store import (
    ensure_db_schema,
    record_render_artifacts,
    set_image_manual_publication_valid,
)
from social_automation.models import Platform
from social_automation.scheduling.prepare_week import prepare_week
from social_automation.settings import Settings


def test_prepare_week_dry_run_with_approved_image(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    img = tmp_path / "food.jpg"
    img.write_bytes(b"img")
    image_id = record_render_artifacts(
        db_path,
        image_name="food",
        image_path=img,
        business_category="food",
        metadata_payload={"platform": Platform.INSTAGRAM.value, "business_category": "food"},
    )
    with __import__("sqlite3").connect(db_path) as conn:
        conn.execute(
            "UPDATE images SET render_ig=1, is_valid_by_quality_evaluation=1, "
            "quality_predicted_class='good', quality_predicted_confidence=0.9 WHERE id=?",
            (image_id,),
        )
    set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
    s = Settings(
        db_path=db_path,
        dispatch_require_approval=True,
        vision_api_key="",
        vision_model="",
    )
    result = prepare_week(
        schedule_path=Path("config/schedule.example.yaml"),
        settings=s,
        start=datetime(2026, 6, 22, 0, 0, tzinfo=UTC),
        days=7,
        dry_run=True,
        try_render=False,
    )
    assert result.planned >= 1
    assert result.assignments
