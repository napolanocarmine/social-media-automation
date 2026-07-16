"""Metriche dashboard e suggerimento prossimo step workflow."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from social_automation.app_timezone import now_app
from social_automation.db.store import (
    count_ai_output_images,
    count_plannable_images,
    ensure_db_schema,
    list_due_events,
)
from social_automation.scheduling.story_rules_dispatch import collect_due_story_rules
from social_automation.services.batches import reconcile_stale_running_batches

SUGGESTED_NEXT_PAGES: dict[str, str] = {
    "output_ai": "② Output AI",
    "approve": "③ Approva",
    "plan": "④ Pianifica",
    "publish": "⑤ Pubblica",
    "select": "① Seleziona",
}


def get_workflow_stats(db_path: Path, settings: Any) -> dict[str, int]:
    """Contatori per home e suggerimento prossimo step."""
    pending_approval = count_ai_output_images(db_path, approval_filter="pending")
    ready_to_plan = count_plannable_images(
        db_path,
        require_quality_pass=False,
        require_manual_publication_valid=True,
    )
    due_dispatch = len(
        list_due_events(db_path, due_before=now_app(settings), limit=200)
    )
    due_story = len(
        collect_due_story_rules(db_path, now=datetime.now(UTC), limit=200)
    )
    processed_visual = count_ai_output_images(db_path, approval_filter="all")
    reconcile_stale_running_batches(db_path)
    running_batches = 0
    try:
        ensure_db_schema(db_path)
        with sqlite3.connect(db_path) as conn:
            row2 = conn.execute(
                "SELECT COUNT(*) FROM batches WHERE status = 'running'"
            ).fetchone()
            running_batches = int(row2[0]) if row2 else 0
    except Exception:
        pass
    return {
        "processed_visual": processed_visual,
        "pending_approval": pending_approval,
        "ready_to_plan": ready_to_plan,
        "due_dispatch": due_dispatch + due_story,
        "running_batches": running_batches,
    }


def suggest_next_page(stats: dict[str, int]) -> str:
    if stats["running_batches"] > 0:
        return SUGGESTED_NEXT_PAGES["output_ai"]
    if stats["pending_approval"] > 0:
        return SUGGESTED_NEXT_PAGES["approve"]
    if stats["ready_to_plan"] > 0:
        return SUGGESTED_NEXT_PAGES["plan"]
    if stats["due_dispatch"] > 0:
        return SUGGESTED_NEXT_PAGES["publish"]
    return SUGGESTED_NEXT_PAGES["select"]
