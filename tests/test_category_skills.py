from __future__ import annotations

from social_automation.brand.feedback_learnings import (
    APPROVAL_FEEDBACK_TAGS,
    format_feedback_learnings_for_prompt,
    normalize_feedback_tags,
)
from social_automation.settings import Settings
from social_automation.visual.category_skills import (
    format_category_skill_for_edit_plan,
    format_category_skill_for_image_edit,
    resolve_category_skill,
)


def test_resolve_category_skill_food() -> None:
    skill = resolve_category_skill("food")
    assert skill.key == "food"
    assert "FOOD" in skill.edit_plan_hints


def test_resolve_category_skill_staff_aliases() -> None:
    assert resolve_category_skill("peppe").key == "staff"
    assert resolve_category_skill("boss").key == "staff"


def test_resolve_category_skill_locale() -> None:
    assert resolve_category_skill("locale").key == "locale"
    assert resolve_category_skill("community").key == "locale"


def test_category_skill_hints_disabled() -> None:
    assert format_category_skill_for_edit_plan("food", enabled=False) == ""
    assert format_category_skill_for_image_edit("food", enabled=False) == ""


def test_normalize_feedback_tags() -> None:
    assert normalize_feedback_tags(["logo_altered", "invalid", "too_hdr"]) == [
        "logo_altered",
        "too_hdr",
    ]


def test_format_feedback_learnings_empty_when_disabled(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    settings = Settings(
        db_path=db_path,
        visual_feedback_learning_enabled=False,
    )
    assert format_feedback_learnings_for_prompt("food", settings=settings) == ""


def test_format_feedback_learnings_from_db(tmp_path) -> None:
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
        reason="Logo Story alterato",
        tags=["logo_altered"],
    )
    settings = Settings(db_path=db_path, visual_feedback_learning_enabled=True)
    text = format_feedback_learnings_for_prompt("food", settings=settings)
    assert "Apprendimenti da approvazioni recenti" in text
    assert "logo_altered" in text
    assert "Logo Story alterato" in text


def test_approval_feedback_tags_catalog() -> None:
    assert "logo_altered" in APPROVAL_FEEDBACK_TAGS
    assert "too_hdr" in APPROVAL_FEEDBACK_TAGS
