from __future__ import annotations

from social_automation.brand.loader import (
    build_brand_context_message,
    build_system_message,
    load_story_agent_config,
)


def test_three_layer_config_loads() -> None:
    cfg = load_story_agent_config()
    assert cfg.name == "Story AI Assistant"
    # Layer 1
    assert "Story AI Assistant" in cfg.system_preamble
    assert "Social Media Manager" in cfg.system_preamble
    assert "MODALITÀ DISPONIBILI" not in cfg.system_preamble
    # Layer 2
    assert "Content Pillars" in cfg.business_rules_text or "Content Pillar" in cfg.business_rules_text
    assert "Tone of Voice" in cfg.business_rules_text
    assert cfg.knowledge_text == cfg.business_rules_text
    # Layer 3
    assert "/produce" in cfg.produce_prompt
    assert "{objective}" in cfg.produce_prompt


def test_system_message_layers_separated() -> None:
    cfg = load_story_agent_config()
    system = build_system_message(cfg)
    brand = build_brand_context_message(cfg)
    assert system == brand
    assert "--- BUSINESS RULES ---" in system
    # Layer 3 template (placeholder) non nel system message
    assert "{objective}" not in system
    assert "la stessa foto scattata meglio" not in system
