from __future__ import annotations

from social_automation.brand.feedback_learnings import format_feedback_learnings_for_prompt
from social_automation.settings import Settings
from social_automation.visual.edit_plan import _enrich_edit_plan_prompt
from social_automation.visual.prompts import _append_category_and_feedback


def test_enrich_edit_plan_includes_food_skill() -> None:
    settings = Settings(visual_category_skills_enabled=True, visual_feedback_learning_enabled=False)
    out = _enrich_edit_plan_prompt(
        "base prompt",
        settings=settings,
        business_category="food",
    )
    assert "Skill categoria FOOD" in out
    assert out.startswith("base prompt")


def test_append_image_edit_includes_staff_skill() -> None:
    settings = Settings(visual_category_skills_enabled=True, visual_feedback_learning_enabled=False)
    out = _append_category_and_feedback(
        "edit task",
        business_category="peppe",
        settings=settings,
    )
    assert "Categoria STAFF" in out


def test_feedback_block_appended_when_present(tmp_path) -> None:
    import sqlite3

    from social_automation.db.store import ensure_db_schema, insert_approval_feedback

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
        tags=["too_hdr"],
    )
    settings = Settings(
        db_path=db_path,
        visual_category_skills_enabled=False,
        visual_feedback_learning_enabled=True,
    )
    feedback = format_feedback_learnings_for_prompt("food", settings=settings)
    out = _enrich_edit_plan_prompt("base", settings=settings, business_category="food")
    assert feedback
    assert feedback in out
