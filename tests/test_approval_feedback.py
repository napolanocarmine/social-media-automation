from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import (
    ensure_db_schema,
    get_feedback_learnings_for_category,
    insert_approval_feedback,
    record_processed_artifacts,
)
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings


def _seed_ai_image(tmp_path: Path) -> tuple[Path, Settings, int]:
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
    return db_path, settings, image_id


def _client(db_path: Path, settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    return TestClient(app)


def test_insert_and_query_feedback_learnings(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(
            "INSERT INTO images(name, path) VALUES (?, ?)",
            ("test.jpg", str(tmp_path / "test.jpg")),
        )
        image_id = int(cur.lastrowid)
    insert_approval_feedback(
        db_path,
        image_id=image_id,
        action="reject",
        business_category="food",
        reason="Troppo HDR",
        tags=["too_hdr"],
    )
    learnings = get_feedback_learnings_for_category(db_path, categories=["food"], limit=3)
    assert len(learnings) == 1
    assert learnings[0]["action"] == "reject"
    assert learnings[0]["tags"] == ["too_hdr"]


def test_approval_with_feedback_tags(tmp_path: Path) -> None:
    db_path, settings, image_id = _seed_ai_image(tmp_path)
    client = _client(db_path, settings)

    tags_resp = client.get("/api/v1/images/approval-feedback-tags")
    assert tags_resp.status_code == 200
    assert "logo_altered" in tags_resp.json()["tags"]

    rejected = client.post(
        f"/api/v1/images/{image_id}/approval",
        json={
            "action": "reject",
            "reason": "Logo alterato",
            "tags": ["logo_altered"],
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval_status"] == "rejected"

    learnings = get_feedback_learnings_for_category(db_path, categories=["food"], limit=5)
    assert len(learnings) == 1
    assert learnings[0]["reason"] == "Logo alterato"
