"""Test riconciliazione batch zombie e copertura route API."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import create_batch, get_batch
from social_automation.models import MediaFormat, Platform
from social_automation.services.batches import get_active_running_batch, reconcile_stale_running_batches
from social_automation.settings import Settings


def _client(db_path, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app)


def test_reconcile_closes_orphan_running_batch(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    batch_id = create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=350,
        media_format=MediaFormat.POST,
    )
    closed = reconcile_stale_running_batches(db_path)
    assert closed == 1
    row = get_batch(db_path, batch_id=batch_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"]


def test_active_batch_none_after_reconcile(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=5,
        media_format=MediaFormat.POST,
    )
    assert get_active_running_batch(db_path) is None


def test_api_routes_smoke(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    sched = tmp_path / "schedule.yaml"
    sched.write_text(
        "timezone: Europe/Rome\nslots: []\n",
        encoding="utf-8",
    )
    settings = Settings(
        db_path=db_path,
        output_dir=out_dir,
        schedule_config_path=sched,
    )
    client = _client(db_path, settings)

    checks: list[tuple[str, str, str | None]] = [
        ("GET", "/api/v1/health", None),
        ("GET", "/api/health", None),
        ("GET", "/api/v1/dashboard/stats", None),
        ("GET", "/api/v1/dashboard/suggested-next-step", None),
        ("GET", "/api/v1/config/categories", None),
        ("GET", "/api/v1/config/marketing-objectives", None),
        ("GET", "/api/v1/config/dispatch", None),
        ("GET", "/api/v1/images/ai-output?filter=all&limit=5", None),
        ("GET", "/api/v1/images/pending-approval?platform=instagram&format=post&category=tutte&page=0", None),
        ("GET", "/api/v1/images/plannable?platform=instagram&format=post&category=tutte&page=0", None),
        ("GET", "/api/v1/drive/assets?category=food&page=0&page_size=5", None),
        ("GET", "/api/v1/batches/active", None),
        ("GET", "/api/v1/batches?limit=5", None),
        ("GET", "/api/v1/dispatch/due?limit=5", None),
        ("GET", "/api/v1/calendar?year=2026&month=6", None),
        ("GET", "/api/v1/calendar/events?year=2026&month=6", None),
        ("POST", "/api/v1/dispatch/dry-run", '{"limit": 5}'),
        ("POST", "/api/v1/automation/prepare-week", '{"days": 7, "dry_run": true, "try_render": false}'),
    ]

    for method, path, body in checks:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.post(
                path,
                content=body or "{}",
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code < 500, f"{method} {path} -> {response.status_code}: {response.text}"

    batch_resp = client.post(
        "/api/v1/batches/ai",
        json={
            "category": "food",
            "platform": "instagram",
            "media_format": "post",
            "assets": [
                {
                    "file_id": "x1",
                    "name": "a.jpg",
                    "mime_type": "image/jpeg",
                }
            ],
        },
    )
    assert batch_resp.status_code == 200
    batch_id = batch_resp.json()["batch_id"]
    assert client.get(f"/api/v1/batches/{batch_id}").status_code == 200
