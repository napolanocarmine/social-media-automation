from __future__ import annotations

from pathlib import Path

from social_automation.db.store import get_copy_pack
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual.models import VisualProductionResult, VisualReview
from social_automation.workflow import process_photo as pp


def test_process_local_photo_v2_mock(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "db.sqlite3"
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"\xff\xd8\xff")
    out_dir = tmp_path / "output"
    final = out_dir / "processed" / "ig" / "food_photo.jpg"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"jpeg")

    settings = Settings(
        db_path=db_path,
        output_dir=out_dir,
        vision_api_key="sk-test",
        vision_model="gpt-test",
    )

    review = VisualReview(
        score=8.5,
        approved=True,
        needs_editing=False,
        reasoning="ok",
        suggested_format="instagram_4_5",
    )
    production = VisualProductionResult(
        final_path=str(final),
        original_path=str(src),
        generated_image_path=None,
        visual_score=8.5,
        visual_status="original",
        editing_required=False,
        method="original",
        review=review,
    )

    def fake_produce(*_a, **_k):
        return production

    def fake_copy(*_a, **_k):
        return {
            "instagram_caption": "Momento Story.",
            "facebook_caption": "Momento Story FB.",
            "hashtags": ["#TuttaNataStory"],
            "final_review": {"status": "APPROVED", "notes": "ok"},
        }

    monkeypatch.setattr(pp, "produce_final_asset", fake_produce)
    monkeypatch.setattr(pp, "generate_copy_pack", fake_copy)

    out = pp.process_local_photo(
        src,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        settings=settings,
        generate_copy=True,
    )
    assert out["image_id"] > 0
    assert out["visual_score"] == 8.5
    pack = get_copy_pack(db_path, image_id=int(out["image_id"]))
    assert pack is not None
    assert pack.get("instagram_caption") == "Momento Story."


def test_process_local_photo_visual_only(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "db.sqlite3"
    src = tmp_path / "photo.jpg"
    src.write_bytes(b"\xff\xd8\xff")
    out_dir = tmp_path / "output"
    final = out_dir / "processed" / "ig" / "food_photo.jpg"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"jpeg")

    settings = Settings(
        db_path=db_path,
        output_dir=out_dir,
        vision_api_key="sk-test",
        vision_model="gpt-test",
    )

    review = VisualReview(
        score=8.5,
        approved=True,
        needs_editing=False,
        reasoning="ok",
        suggested_format="instagram_4_5",
    )
    production = VisualProductionResult(
        final_path=str(final),
        original_path=str(src),
        generated_image_path=None,
        visual_score=8.5,
        visual_status="original",
        editing_required=False,
        method="original",
        review=review,
    )

    def fake_produce(*_a, **_k):
        return production

    def fail_copy(*_a, **_k):
        raise AssertionError("copy must not run when generate_copy=False")

    monkeypatch.setattr(pp, "produce_final_asset", fake_produce)
    monkeypatch.setattr(pp, "generate_copy_pack", fail_copy)

    out = pp.process_local_photo(
        src,
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        business_category="food",
        settings=settings,
        generate_copy=False,
    )
    assert out["image_id"] > 0
    assert get_copy_pack(db_path, image_id=int(out["image_id"])) is None
