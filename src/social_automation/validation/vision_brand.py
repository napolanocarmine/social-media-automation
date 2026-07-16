"""Caricamento prompt brand per validazione vision."""

from __future__ import annotations

from pathlib import Path

import yaml

from social_automation.settings import repo_root

_DEFAULT_REL = Path("config/vision_brand.yaml")


def load_vision_brand_instructions(
    config_path: Path | None = None,
    *,
    category: str | None = None,
) -> str:
    """Istruzioni per il modello vision (default + override per categoria business)."""
    path = config_path
    if path is None or not path.is_file():
        path = repo_root() / _DEFAULT_REL
    if not path.is_file():
        path = repo_root() / Path("config/vision_brand.example.yaml")
    if not path.is_file():
        return (
            "Valuta se l'immagine è adatta alla pubblicazione su social media. "
            'Rispondi SOLO con JSON: {"pass": true|false, "reason": "..."}'
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = str(data.get("default_instructions") or "").strip()
    overrides = data.get("category_overrides") or {}
    cat = (category or "").strip().lower()
    if cat and isinstance(overrides, dict):
        extra = str(overrides.get(cat) or "").strip()
        if extra:
            return f"{base}\n\nIstruzioni specifiche categoria «{cat}»:\n{extra}"
    return base
