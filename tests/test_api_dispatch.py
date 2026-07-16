from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import add_planning_event, ensure_db_schema, record_render_artifacts
from social_automation.models import Platform
from social_automation.settings import Settings


def _client(tmp_path: Path) -> tuple[TestClient, Path, Settings]:
    db_path = tmp_path / "db.sqlite3"
    sched = tmp_path / "schedule.yaml"
    shutil.copy(Path("config/schedule.example.yaml"), sched)
    settings = Settings(db_path=db_path, schedule_config_path=sched)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app), db_path, settings


def test_dispatch_due_empty(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    response = client.get("/api/v1/dispatch/due")
    assert response.status_code == 200
    body = response.json()
    assert body["planning_count"] == 0
    assert body["story_count"] == 0


def test_dispatch_due_with_event(tmp_path: Path) -> None:
    client, db_path, _ = _client(tmp_path)
    ensure_db_schema(db_path)
    img = tmp_path / "p.jpg"
    img.write_bytes(b"x")
    image_id = record_render_artifacts(
        db_path,
        image_name="p",
        image_path=img,
        metadata_payload={"platform": "instagram"},
    )
    add_planning_event(
        db_path,
        image_id=image_id,
        platform=Platform.INSTAGRAM,
        event_type="planned",
        scheduled_for=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
    )
    response = client.get("/api/v1/dispatch/due")
    assert response.status_code == 200
    assert response.json()["planning_count"] == 1


def test_dispatch_dry_run(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post("/api/v1/dispatch/dry-run", json={"limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True


def test_prepare_week_dry_run(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post(
        "/api/v1/automation/prepare-week",
        json={"days": 7, "dry_run": True, "try_render": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert "message" in body


def test_batches_list(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    response = client.get("/api/v1/batches?limit=10")
    assert response.status_code == 200
    assert response.json() == []
