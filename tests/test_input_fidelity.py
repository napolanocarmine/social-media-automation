from __future__ import annotations

import pytest

from social_automation.settings import Settings
from social_automation.visual.input_fidelity import (
    normalize_input_fidelity,
    settings_with_input_fidelity,
)


def test_normalize_input_fidelity_accepts_high_and_low() -> None:
    assert normalize_input_fidelity("high") == "high"
    assert normalize_input_fidelity("LOW") == "low"


def test_normalize_input_fidelity_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="high, low"):
        normalize_input_fidelity("medium")


def test_settings_with_input_fidelity_overrides() -> None:
    base = Settings(visual_image_input_fidelity="low")
    out = settings_with_input_fidelity(base, "high")
    assert out.visual_image_input_fidelity == "high"
    assert out is not base


def test_settings_with_input_fidelity_noop_when_empty() -> None:
    base = Settings(visual_image_input_fidelity="low")
    assert settings_with_input_fidelity(base, None) is base
    assert settings_with_input_fidelity(base, "") is base
