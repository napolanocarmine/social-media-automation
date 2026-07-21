from __future__ import annotations

from unittest.mock import patch

from social_automation.services.batch_queue import process_batch_queue
from social_automation.settings import Settings


def test_process_batch_queue_stops_on_empty_queue(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "db.sqlite3", output_dir=tmp_path / "output")
    with patch(
        "social_automation.services.batch_queue.process_next_batch_item",
        side_effect=[
            {"batch_id": 1, "status": "completed", "image_id": 10},
            {"message": "Nessun item in coda"},
        ],
    ) as mock_next:
        results = process_batch_queue(settings, max_items=5)
    assert len(results) == 2
    assert mock_next.call_count == 2
