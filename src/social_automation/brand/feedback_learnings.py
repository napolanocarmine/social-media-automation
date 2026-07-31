"""Aggregazione feedback approvazioni → hint per prompt pipeline."""

from __future__ import annotations

from pathlib import Path

from social_automation.settings import Settings, load_settings

APPROVAL_FEEDBACK_TAGS: dict[str, str] = {
    "logo_altered": "Logo o testo brand alterato",
    "wrong_crop": "Crop / inquadratura sbagliata",
    "too_hdr": "Troppo contrasto / look HDR o AI",
    "face_unnatural": "Volto o pelle non naturale",
    "background_regenerated": "Sfondo rigenerato / bokeh artificiale",
    "food_not_sharp": "Cibo non abbastanza nitido",
    "elements_missing": "Elementi persi (patatine, bandierina, …)",
    "other": "Altro",
}


def normalize_feedback_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    allowed = set(APPROVAL_FEEDBACK_TAGS)
    out: list[str] = []
    for raw in tags:
        key = str(raw or "").strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    return out


def _category_keys_for_business_category(business_category: str | None) -> list[str]:
    cat = (business_category or "").strip().lower()
    if cat in {"food", "birra", "beer"}:
        return ["food", "birra", "beer"]
    if cat in {"boss", "peppe", "staff"}:
        return ["boss", "peppe", "staff"]
    if cat in {"locale", "community"}:
        return ["locale", "community"]
    if cat:
        return [cat]
    return []


def format_feedback_learnings_for_prompt(
    business_category: str | None,
    *,
    settings: Settings | None = None,
    db_path: Path | None = None,
) -> str:
    """Restituisce apprendimenti recenti da reject/approve per la famiglia di categoria."""
    s = settings or load_settings()
    if not s.visual_feedback_learning_enabled:
        return ""
    from social_automation.db.store import get_feedback_learnings_for_category

    path = db_path or s.db_path
    cat_keys = _category_keys_for_business_category(business_category)
    learnings = get_feedback_learnings_for_category(
        path,
        categories=cat_keys,
        limit=int(s.visual_feedback_learning_max_items),
    )
    if not learnings:
        return ""

    lines = ["--- Apprendimenti da approvazioni recenti (stessa famiglia categoria) ---"]
    for item in learnings:
        action = str(item.get("action") or "").strip()
        tags = item.get("tags") or []
        reason = str(item.get("reason") or "").strip()
        tag_text = ", ".join(str(t) for t in tags if str(t).strip())
        parts = [f"- [{action}]"]
        if tag_text:
            parts.append(f"tag: {tag_text}")
        if reason:
            parts.append(reason)
        lines.append(" ".join(parts))

    lines.append(
        "Usa questi feedback per evitare errori ripetuti (logo alterato, crop errato, tono HDR, ecc.)."
    )
    return "\n".join(lines).strip()
