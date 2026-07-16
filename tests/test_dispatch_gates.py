from __future__ import annotations

from social_automation.scheduling.dispatch_gates import check_image_dispatch_gates
from social_automation.settings import Settings


def test_dispatch_blocks_without_approval() -> None:
    s = Settings(dispatch_require_approval=True, dispatch_require_quality_pass=False)
    ok, reason = check_image_dispatch_gates({"is_valid_for_publication": None}, s)
    assert not ok
    assert "approvazione" in (reason or "").lower()


def test_dispatch_passes_when_gates_disabled() -> None:
    s = Settings(
        dispatch_require_approval=False,
        dispatch_require_quality_pass=False,
        dispatch_require_vision_pass=False,
    )
    ok, reason = check_image_dispatch_gates({}, s)
    assert ok
    assert reason is None


def test_dispatch_requires_quality_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "social_automation.scheduling.dispatch_gates.quality_gate_configured",
        lambda _s: True,
    )
    s = Settings(
        dispatch_require_approval=False,
        dispatch_require_quality_pass=True,
        dispatch_require_vision_pass=False,
    )
    ok, _ = check_image_dispatch_gates({"is_valid_by_quality_evaluation": 0}, s)
    assert not ok
    ok2, _ = check_image_dispatch_gates({"is_valid_by_quality_evaluation": 1}, s)
    assert ok2
