from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import add_batch_item, create_batch, get_batch, list_batch_items
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings


def _client(db_path, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app)


def test_start_ai_batch_creates_running_batch(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    settings = Settings(db_path=db_path, output_dir=out_dir)
    client = _client(db_path, settings)

    assets = [
        {
            "file_id": "abc123",
            "name": "photo.jpg",
            "mime_type": "image/jpeg",
            "path_segments": ["2025", "06", "food"],
        }
    ]
    with patch(
        "social_automation.api.routers.batches.process_batch_queue",
    ) as mock_process:
        response = client.post(
            "/api/v1/batches/ai",
            json={
                "category": "food",
                "platform": "instagram",
                "media_format": "post",
                "assets": assets,
            },
        )
    assert response.status_code == 200
    batch_id = response.json()["batch_id"]
    mock_process.assert_called_once()
    row = get_batch(db_path, batch_id=batch_id)
    assert row is not None
    assert row["status"] == "running"
    items = list_batch_items(db_path, batch_id=batch_id)
    assert len(items) == 1
    assert items[0]["status"] == "queued"


def test_start_ai_batch_skips_auto_process_when_disabled(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    settings = Settings(db_path=db_path, output_dir=out_dir, batch_auto_process=False)
    client = _client(db_path, settings)

    assets = [
        {
            "file_id": "abc123",
            "name": "photo.jpg",
            "mime_type": "image/jpeg",
            "path_segments": ["2025", "06", "food"],
        }
    ]
    with patch("social_automation.api.routers.batches.process_batch_queue") as mock_process:
        response = client.post(
            "/api/v1/batches/ai",
            json={
                "category": "food",
                "platform": "instagram",
                "media_format": "post",
                "assets": assets,
            },
        )
    assert response.status_code == 200
    mock_process.assert_not_called()


def test_active_batch_and_stop(tmp_path) -> None:

    db_path = tmp_path / "db.sqlite3"
    settings = Settings(db_path=db_path, output_dir=tmp_path / "output")
    batch_id = create_batch(
        db_path,
        category="food",
        platform=Platform.INSTAGRAM,
        requested_count=2,
        media_format=MediaFormat.POST,
    )
    add_batch_item(
        db_path,
        batch_id=batch_id,
        item_index=1,
        status="queued",
        source_asset_id="x",
        source_asset_name="y",
        media_format=MediaFormat.POST,
    )
    client = _client(db_path, settings)

    active = client.get("/api/v1/batches/active")
    assert active.status_code == 200
    assert active.json()["id"] == batch_id

    detail = client.get(f"/api/v1/batches/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["batch"]["requested_count"] == 2

    stopped = client.post(f"/api/v1/batches/{batch_id}/stop", json={"reason": "test"})
    assert stopped.status_code == 200
    assert stopped.json()["stop_requested"] is True


def test_config_categories() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/config/categories")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["categories"], list)
    assert len(body["categories"]) >= 1
