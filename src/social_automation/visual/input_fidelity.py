"""Normalizzazione input_fidelity per gpt-image-1/1.5."""

from __future__ import annotations

from social_automation.settings import Settings

INPUT_FIDELITY_OPTIONS: tuple[str, ...] = ("high", "low")

INPUT_FIDELITY_LABELS: dict[str, str] = {
    "high": "Alta — preserva pixel originali (edit sottile)",
    "low": "Bassa — generazione parziale più visibile",
}


def normalize_input_fidelity(value: str | None, *, default: str = "low") -> str:
    candidate = (value or default).strip().lower()
    if candidate not in INPUT_FIDELITY_OPTIONS:
        allowed = ", ".join(INPUT_FIDELITY_OPTIONS)
        raise ValueError(f"input_fidelity deve essere uno tra: {allowed}")
    return candidate


def settings_with_input_fidelity(
    settings: Settings,
    fidelity: str | None,
) -> Settings:
    if fidelity is None or not str(fidelity).strip():
        return settings
    normalized = normalize_input_fidelity(
        fidelity,
        default=settings.visual_image_input_fidelity,
    )
    if normalized == settings.visual_image_input_fidelity:
        return settings
    return settings.model_copy(update={"visual_image_input_fidelity": normalized})
