from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.brand.copy_pack import planning_detail_with_caption
from social_automation.db.store import (
    add_planning_event,
    record_processed_artifacts,
    set_image_manual_publication_valid,
    update_image_copy_json,
)
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings


def _seed_plannable(tmp_path: Path) -> tuple[Path, Settings, int]:
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    src = out_dir / "drive_abc.jpg"
    Image.new("RGB", (40, 30), color=(100, 50, 20)).save(src, format="JPEG")
    dest = out_dir / "processed" / "ig" / "food_abc.jpg"
    dest.parent.mkdir(parents=True)
    Image.new("RGB", (40, 30), color=(200, 150, 100)).save(dest, format="JPEG")

    db_path = tmp_path / "db.sqlite3"
    sched = tmp_path / "schedule.yaml"
    shutil.copy(Path("config/schedule.example.yaml"), sched)
    settings = Settings(db_path=db_path, output_dir=out_dir, schedule_config_path=sched)
    image_id = record_processed_artifacts(
        db_path,
        image_name="food_abc.jpg",
        image_path=dest,
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "media_format": MediaFormat.POST.value,
            "source_file": str(src),
            "visual_method": "ai_edited",
        },
        original_path=str(src),
        visual_score=7.5,
        visual_status="ai_editing",
        editing_required=True,
        business_category="food",
    )
    set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
    update_image_copy_json(
        db_path,
        image_id=image_id,
        copy_json={
            "instagram_caption": "Caption test",
            "hashtags": ["#food"],
        },
    )
    return db_path, settings, image_id


def _client(db_path: Path, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app)


def test_plannable_list(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_plannable(tmp_path)
    client = _client(db_path, settings)
    response = client.get(
        "/api/v1/images/plannable?platform=instagram&format=post&category=tutte&page=0"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == image_id


def test_suggest_slot(tmp_path: Path) -> None:
    db_path, settings, _image_id = _seed_plannable(tmp_path)
    client = _client(db_path, settings)
    response = client.post("/api/v1/plans/suggest-slot", json={"platform": "instagram"})
    assert response.status_code == 200
    body = response.json()
    assert body is None or "scheduled_date" in body


def test_create_and_calendar(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_plannable(tmp_path)
    client = _client(db_path, settings)
    created = client.post(
        "/api/v1/plans",
        json={
            "image_id": image_id,
            "platform": "instagram",
            "media_format": "post",
            "scheduled_date": "2026-07-01",
            "scheduled_time": "12:30",
            "caption": "Caption test",
        },
    )
    assert created.status_code == 200
    assert created.json()["image_id"] == image_id

    cal = client.get("/api/v1/calendar?year=2026&month=7")
    assert cal.status_code == 200
    assert cal.json()["total"] >= 1


def test_reschedule_and_cancel(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_plannable(tmp_path)
    from datetime import UTC, datetime

    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        event_type="planned",
        scheduled_for=datetime(2026, 7, 2, 10, 30, tzinfo=UTC),
        detail=planning_detail_with_caption("Old caption"),
    )
    client = _client(db_path, settings)

    rescheduled = client.patch(
        f"/api/v1/plans/{image_id}/instagram",
        json={
            "scheduled_date": "2026-07-03",
            "scheduled_time": "14:00",
            "caption": "New caption",
        },
    )
    assert rescheduled.status_code == 200

    cancelled = client.delete(f"/api/v1/plans/{image_id}/instagram")
    assert cancelled.status_code == 200
    assert "annullata" in cancelled.json()["message"].lower()
