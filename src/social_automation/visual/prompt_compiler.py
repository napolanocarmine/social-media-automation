"""Compila/ottimizza il prompt image edit via LLM testuale (simula mainline ChatGPT)."""

from __future__ import annotations

import logging

from social_automation.brand.openai_json import api_configured, chat_text
from social_automation.settings import Settings
from social_automation.visual.models import ImageEditPlan

_LOG = logging.getLogger(__name__)

_COMPILER_SYSTEM = (
    "You optimize prompts for OpenAI gpt-image-1.5 in EDIT mode (not generation). "
    "The model must preserve the original photograph: faces, logos, flags, food shape, "
    "background bokeh. Output ONLY the final English prompt for the image tool — no preamble, "
    "no markdown, no JSON. Keep all preserve/forbid rules. Be specific about selective "
    "sharpness targets. If the input says crop is already done, do NOT ask for cropping. "
    "If tone/exposure is handled separately, do NOT ask for global brightness changes."
)


def compile_image_edit_prompt(
    draft_prompt: str,
    *,
    settings: Settings,
    edit_plan: ImageEditPlan | None = None,
) -> str:
    """
    Riscrive il prompt draft per il tool image (opzionale, come ChatGPT mainline).

    In caso di errore restituisce il draft invariato.
    """
    draft = (draft_prompt or "").strip()
    if not draft:
        return draft
    compiler_model = (settings.visual_responses_model or "").strip()
    if not settings.visual_edit_prompt_compiler:
        return draft
    if not api_configured(api_key=settings.vision_api_key, model=compiler_model):
        _LOG.warning("Prompt compiler disabilitato: modello non configurato")
        return draft

    plan_hint = ""
    if edit_plan and edit_plan.has_content:
        targets = ", ".join(edit_plan.sharpness_targets) or "main subject"
        plan_hint = (
            f"\nSharpness targets for this photo: {targets}. "
            f"Preserve elements: {', '.join(edit_plan.preserve_elements) or 'n/a'}."
        )

    user = (
        "Rewrite this image EDIT prompt for gpt-image-1.5. "
        "Keep it concise but complete. English only.\n\n"
        f"--- DRAFT ---\n{draft}{plan_hint}\n--- END ---"
    )
    try:
        compiled = chat_text(
            system_message=_COMPILER_SYSTEM,
            user_prompt=user,
            api_key=settings.vision_api_key,
            model=compiler_model,
            api_base_url=settings.vision_api_base_url,
            max_tokens=1800,
            settings=settings,
        )
        if compiled:
            _LOG.info(
                "Prompt compiler: draft_len=%s compiled_len=%s",
                len(draft),
                len(compiled),
            )
            return compiled
    except Exception as exc:
        _LOG.warning("Prompt compiler fallito, uso draft: %s", exc)
    return draft
