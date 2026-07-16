from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import record_processed_artifacts
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings


def _seed_ai_image(tmp_path: Path, *, pending: bool = True) -> tuple[Path, Settings, int]:
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    src = out_dir / "drive_abc.jpg"
    Image.new("RGB", (40, 30), color=(100, 50, 20)).save(src, format="JPEG")
    dest = out_dir / "processed" / "ig" / "food_abc.jpg"
    dest.parent.mkdir(parents=True)
    Image.new("RGB", (40, 30), color=(200, 150, 100)).save(dest, format="JPEG")

    db_path = tmp_path / "db.sqlite3"
    settings = Settings(db_path=db_path, output_dir=out_dir)
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
    if not pending:
        from social_automation.db.store import set_image_manual_publication_valid

        set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
    return db_path, settings, image_id


def _client(db_path: Path, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app)


def test_ai_output_list(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_ai_image(tmp_path)
    client = _client(db_path, settings)
    response = client.get("/api/v1/images/ai-output?filter=pending")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == image_id
    assert body["items"][0]["approval_status"] == "pending"


def test_pending_approval_and_approve(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_ai_image(tmp_path)
    client = _client(db_path, settings)

    listing = client.get(
        "/api/v1/images/pending-approval"
        "?platform=instagram&format=post&category=tutte&page=0"
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    approved = client.post(
        f"/api/v1/images/{image_id}/approval",
        json={"action": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"

    pending = client.get("/api/v1/images/ai-output?filter=pending")
    assert pending.json()["total"] == 0


def test_media_endpoints(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_ai_image(tmp_path)
    client = _client(db_path, settings)

    processed = client.get(f"/api/v1/media/images/{image_id}/processed")
    assert processed.status_code == 200
    assert processed.headers["content-type"].startswith("image/")

    original = client.get(f"/api/v1/media/images/{image_id}/original")
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("image/")
