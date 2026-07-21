"""Gate di sicurezza prima della pubblicazione automatica (dispatch)."""

from __future__ import annotations

from typing import Any

from social_automation.image_quality_onnx import quality_gate_configured
from social_automation.settings import Settings


def dispatch_gates_active(settings: Settings) -> dict[str, bool]:
    """Quali gate sono attivi in base alle impostazioni e alla configurazione."""
    quality_on = bool(settings.dispatch_require_quality_pass) and quality_gate_configured(settings)
    return {
        "approval": bool(settings.dispatch_require_approval),
        "quality": quality_on,
        # Gate vision brand disattivato temporaneamente: non blocca il dispatch.
        # Per riattivarlo, decommentare e impostare dispatch_require_vision_pass=true.
        # "vision": bool(settings.dispatch_require_vision_pass)
        # and vision_validation_configured(
        #     api_key=settings.vision_api_key,
        #     model=settings.vision_model,
        # ),
        "vision": False,
    }


def check_image_dispatch_gates(
    image_row: dict[str, Any],
    settings: Settings,
) -> tuple[bool, str | None]:
    """
  Valuta se un'immagine può essere pubblicata dal dispatch automatico.

  ``image_row`` deve contenere le colonne ``images`` rilevanti
  (``is_valid_for_publication``, ``is_valid_by_quality_evaluation``, ``vision_eval_pass``).
  """
    gates = dispatch_gates_active(settings)
    if gates["approval"]:
        manual = image_row.get("is_valid_for_publication")
        if manual is None:
            return False, "approvazione manuale mancante (is_valid_for_publication NULL)"
        if int(manual) != 1:
            return False, "approvazione manuale negata o non impostata (is_valid_for_publication != 1)"

    if gates["quality"]:
        q = image_row.get("is_valid_by_quality_evaluation")
        if q is None:
            return False, "valutazione qualità ONNX assente"
        if int(q) != 1:
            return False, "qualità ONNX insufficiente (is_valid_by_quality_evaluation != 1)"

    # Gate vision brand disattivato temporaneamente (vedi dispatch_gates_active).
    # if gates["vision"]:
    #     v = image_row.get("vision_eval_pass")
    #     if v is None:
    #         return False, "valutazione vision brand assente"
    #     if int(v) != 1:
    #         reason = str(image_row.get("vision_eval_reason") or "").strip()
    #         detail = f"vision brand negata (vision_eval_pass != 1)"
    #         if reason:
    #             detail = f"{detail}: {reason}"
    #         return False, detail

    return True, None
