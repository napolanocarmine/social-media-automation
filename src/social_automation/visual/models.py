"""Modelli dati per Visual Producer V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VisualReview:
    score: float
    approved: bool
    needs_editing: bool
    reasoning: str
    suggested_format: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualReview:
        score_raw = data.get("score", data.get("quality_score", 0))
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0
        approved = bool(data.get("approved", score >= 8.0))
        needs_editing = bool(data.get("needs_editing", score < 8.0))
        reasoning = str(data.get("reasoning") or data.get("notes") or "").strip()
        suggested = str(
            data.get("suggested_format")
            or data.get("format_recommendation")
            or "instagram_4_5"
        ).strip()
        return cls(
            score=score,
            approved=approved,
            needs_editing=needs_editing,
            reasoning=reasoning,
            suggested_format=suggested,
        )


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _coerce_bounded_float(
    value: Any,
    *,
    default: float = 0.0,
    lo: float = -0.15,
    hi: float = 0.15,
) -> float:
    if value is None:
        return default
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


@dataclass(frozen=True)
class LightAdjustments:
    """Parametri tono/luce deterministici (Pillow), come run_retouch_analysis."""

    exposure: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    sharpness: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LightAdjustments:
        if not isinstance(data, dict):
            return cls()
        return cls(
            exposure=_coerce_bounded_float(data.get("exposure")),
            contrast=_coerce_bounded_float(data.get("contrast")),
            saturation=_coerce_bounded_float(
                data.get("saturation"), lo=-0.1, hi=0.1
            ),
            sharpness=_coerce_bounded_float(
                data.get("sharpness"), lo=0.0, hi=0.3
            ),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "exposure": self.exposure,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "sharpness": self.sharpness,
        }

    @property
    def has_tone(self) -> bool:
        return any(
            abs(v) > 0.001
            for v in (self.exposure, self.contrast, self.saturation)
        )

    @property
    def has_any(self) -> bool:
        return self.has_tone or self.sharpness > 0.001


@dataclass(frozen=True)
class ImageEditPlan:
    """Piano editing foto-specifico (vision pre-edit, come Custom GPT)."""

    subjects: tuple[str, ...]
    preserve_elements: tuple[str, ...]
    crop_plan: str
    sharpness_targets: tuple[str, ...]
    preserve_soft_background: bool
    adjustments_notes: str
    reasoning: str
    light_adjustments: LightAdjustments

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageEditPlan:
        la_raw = data.get("light_adjustments")
        if not isinstance(la_raw, dict):
            la_raw = {
                k: data.get(k)
                for k in ("exposure", "contrast", "saturation", "sharpness")
                if data.get(k) is not None
            }
        return cls(
            subjects=tuple(_coerce_str_list(data.get("subjects"))),
            preserve_elements=tuple(_coerce_str_list(data.get("preserve_elements"))),
            crop_plan=str(data.get("crop_plan") or "").strip(),
            sharpness_targets=tuple(_coerce_str_list(data.get("sharpness_targets"))),
            preserve_soft_background=bool(data.get("preserve_soft_background", False)),
            adjustments_notes=str(data.get("adjustments_notes") or "").strip(),
            reasoning=str(data.get("reasoning") or "").strip(),
            light_adjustments=LightAdjustments.from_dict(la_raw),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subjects": list(self.subjects),
            "preserve_elements": list(self.preserve_elements),
            "crop_plan": self.crop_plan,
            "sharpness_targets": list(self.sharpness_targets),
            "preserve_soft_background": self.preserve_soft_background,
            "adjustments_notes": self.adjustments_notes,
            "reasoning": self.reasoning,
            "light_adjustments": self.light_adjustments.to_dict(),
        }

    @property
    def has_content(self) -> bool:
        return bool(
            self.subjects
            or self.crop_plan
            or self.sharpness_targets
            or self.preserve_elements
            or self.adjustments_notes
            or self.light_adjustments.has_any
        )


@dataclass(frozen=True)
class ImageEditApiResult:
    """Esito chiamata edit immagine (path + metadati diagnostici API)."""

    path: Path
    revised_prompt: str | None = None


@dataclass(frozen=True)
class VisualDecision:
    use_original: bool
    needs_ai_editing: bool
    needs_manual_review: bool
    visual_status: str


@dataclass(frozen=True)
class VisualProductionResult:
    final_path: str
    original_path: str
    generated_image_path: str | None
    visual_score: float
    visual_status: str
    editing_required: bool
    method: str
    review: VisualReview
    retouch_json: dict[str, Any] | None = None
    producer_notes: str = ""
    edit_plan_json: dict[str, Any] | None = None
