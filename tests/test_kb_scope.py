from __future__ import annotations

from social_automation.brand.kb_scope import KbScope, filter_business_rules


def test_filter_business_rules_copy_excludes_editing_sections() -> None:
    text = """# 1. Overview
Overview text

# 6. Tone of Voice
Tone text

# 15. Regole di Analisi Immagini
Analysis text

# 17. Editing Fotografico
Editing text"""
    filtered = filter_business_rules(text, KbScope.COPY)
    assert "Tone of Voice" in filtered
    assert "Overview" in filtered
    assert "Editing Fotografico" not in filtered
    assert "Regole di Analisi" not in filtered


def test_filter_business_rules_edit_plan_minimal() -> None:
    text = """# 6. Tone of Voice
Tone

# 8. Content Pillars
Pillars

# 16. Regole di Crop
Crop"""
    filtered = filter_business_rules(text, KbScope.EDIT_PLAN)
    assert "Content Pillars" in filtered
    assert "Regole di Crop" in filtered
    assert "Tone of Voice" not in filtered


def test_filter_business_rules_full_returns_all() -> None:
    text = "# 1. A\n\n# 2. B"
    assert filter_business_rules(text, KbScope.FULL) == text
