"""Verifica binding BOOLEAN su Postgres (no int/smallint ai parametri)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social_automation.db.postgres_store import pg_bool_param
from tests.db_test_helpers import fetchone_sql, is_postgres_backend


def test_pg_bool_param_coerces_sqlite_style_ints() -> None:
    assert pg_bool_param(True) is True
    assert pg_bool_param(False) is False
    assert pg_bool_param(1) is True
    assert pg_bool_param(0) is False
    assert pg_bool_param(None) is None


def test_pg_bool_param_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        pg_bool_param(2)


def test_update_vision_eval_binds_python_bool() -> None:
    from contextlib import contextmanager

    from social_automation.db import postgres_store

    captured: list[tuple] = []

    class _Conn:
        def execute(self, sql: str, params: tuple | None = None):
            captured.append((sql, params))
            return MagicMock()

    @contextmanager
    def fake_connect(_db_path=None):
        yield _Conn()

    with (
        patch.object(postgres_store, "ensure_db_schema"),
        patch.object(postgres_store, "_connect", fake_connect),
    ):
        postgres_store.update_vision_eval(
            Path("ignored"),
            image_id=42,
            vision_pass=1,
            reason="ok",
        )

    assert captured
    _sql, params = captured[-1]
    assert params is not None
    assert params[0] is True
    assert isinstance(params[0], bool)


def test_set_image_manual_publication_valid_binds_python_bool() -> None:
    from contextlib import contextmanager

    from social_automation.db import postgres_store

    captured: list[tuple] = []

    class _Conn:
        def execute(self, sql: str, params: tuple | None = None):
            captured.append((sql, params))
            return MagicMock()

    @contextmanager
    def fake_connect(_db_path=None):
        yield _Conn()

    with (
        patch.object(postgres_store, "ensure_db_schema"),
        patch.object(postgres_store, "_connect", fake_connect),
    ):
        postgres_store.set_image_manual_publication_valid(
            Path("ignored"),
            image_id=7,
            value=0,
        )

    assert captured
    _sql, params = captured[-1]
    assert params == (False, 7)
    assert isinstance(params[0], bool)


@pytest.mark.skipif(
    not is_postgres_backend()
    or not (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")),
    reason="Postgres TEST_DATABASE_URL required",
)
def test_postgres_boolean_columns_accept_native_bool(db_path: Path) -> None:
    """Smoke test reale su Neon: tutte le write BOOLEAN del flusso Story AI."""
    from social_automation.db import postgres_store
    from social_automation.db.store import (
        record_processed_artifacts,
        set_image_manual_publication_valid,
        update_image_visual_state,
        update_vision_eval,
    )

    out = db_path.parent / "out"
    out.mkdir(exist_ok=True)
    processed = out / "processed.jpg"
    processed.write_bytes(b"fake-jpeg")

    image_id = record_processed_artifacts(
        db_path,
        image_name="story_test.jpg",
        image_path=processed,
        metadata_payload={"platform": "instagram", "media_format": "story"},
        visual_score=8.0,
        visual_status="ai_edited",
        editing_required=True,
    )

    update_vision_eval(db_path, image_id=image_id, vision_pass=1, reason="brand ok")
    set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
    update_image_visual_state(
        db_path,
        image_id=image_id,
        visual_status="ready",
        editing_required=False,
    )

    with postgres_store._connect(db_path) as conn:
        conn.execute(
            """
            UPDATE images
            SET is_valid_by_quality_evaluation = %s,
                quality_predicted_class = %s,
                quality_predicted_confidence = %s
            WHERE id = %s
            """,
            (
                pg_bool_param(1),
                "good",
                0.91,
                image_id,
            ),
        )

    row = fetchone_sql(
        db_path,
        """
        SELECT editing_required, vision_eval_pass, is_valid_for_publication,
               is_valid_by_quality_evaluation
        FROM images WHERE id = ?
        """,
        (image_id,),
    )
    assert row is not None
    editing_required, vision_pass, pub_valid, quality_valid = row
    assert editing_required in (False, 0)
    assert vision_pass in (True, 1)
    assert pub_valid in (True, 1)
    assert quality_valid in (True, 1)
