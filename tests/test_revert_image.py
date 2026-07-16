from __future__ import annotations

from pathlib import Path

from PIL import Image

from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.workflow.process_photo import revert_image_to_original


def test_revert_image_to_original(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    src = out_dir / "drive_abc.jpg"
    Image.new("RGB", (80, 60), color=(120, 80, 40)).save(src, format="JPEG")
    dest = out_dir / "processed" / "ig" / "food_abc.jpg"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"processed")

    from social_automation.db.store import get_image_record, record_processed_artifacts

    settings = Settings(db_path=db_path, output_dir=out_dir)
    image_id = record_processed_artifacts(
        db_path,
        image_name="test.jpg",
        image_path=dest,
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "media_format": MediaFormat.POST.value,
            "source_file": str(src),
            "visual_method": "ai_edited",
        },
        original_path=str(src),
        visual_score=6.0,
        visual_status="ai_editing",
        editing_required=True,
    )

    out = revert_image_to_original(image_id, settings=settings, approve=True)
    assert out == dest
    assert dest.is_file()
    assert dest.read_bytes() != b"processed"

    row = get_image_record(db_path, image_id=image_id)
    assert row is not None
    assert row["visual_status"] == "original_manual"
    assert int(row["is_valid_for_publication"]) == 1
