from __future__ import annotations

from social_automation.services.dashboard import get_workflow_stats, suggest_next_page
from social_automation.settings import Settings


def test_suggest_next_page_priority() -> None:
    assert suggest_next_page({"running_batches": 1, "pending_approval": 5}) == "② Output AI"
    assert suggest_next_page({"running_batches": 0, "pending_approval": 2}) == "③ Approva"
    assert suggest_next_page({"running_batches": 0, "pending_approval": 0, "ready_to_plan": 1}) == "④ Pianifica"
    assert suggest_next_page(
        {"running_batches": 0, "pending_approval": 0, "ready_to_plan": 0, "due_dispatch": 1}
    ) == "⑤ Pubblica"
    assert suggest_next_page(
        {
            "running_batches": 0,
            "pending_approval": 0,
            "ready_to_plan": 0,
            "due_dispatch": 0,
        }
    ) == "① Seleziona"


def test_get_workflow_stats_empty_db(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    settings = Settings(db_path=db_path)
    stats = get_workflow_stats(db_path, settings)
    assert stats == {
        "processed_visual": 0,
        "pending_approval": 0,
        "ready_to_plan": 0,
        "due_dispatch": 0,
        "running_batches": 0,
    }
