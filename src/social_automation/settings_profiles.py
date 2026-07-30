"""Preset configurazione pipeline visuale Story AI."""

from __future__ import annotations

import os
from typing import Any

from social_automation.settings import Settings

# Env espliciti hanno sempre priorità sul profilo.
_PROFILE_ENV_KEYS: dict[str, str] = {
    "visual_produce_mode": "VISUAL_PRODUCE_MODE",
    "visual_review_enabled": "VISUAL_REVIEW_ENABLED",
    "visual_edit_plan_enabled": "VISUAL_EDIT_PLAN_ENABLED",
    "visual_edit_prompt_compiler": "VISUAL_EDIT_PROMPT_COMPILER",
    "visual_use_ai_image_edit": "VISUAL_USE_AI_IMAGE_EDIT",
    "visual_edit_include_kb": "VISUAL_EDIT_INCLUDE_KB",
    "visual_kb_scope_enabled": "VISUAL_KB_SCOPE_ENABLED",
    "visual_parallel_copy": "VISUAL_PARALLEL_COPY",
    "visual_smart_routing": "VISUAL_SMART_ROUTING",
    "visual_pipeline_trace": "VISUAL_PIPELINE_TRACE",
    "visual_gpt_pure_mode": "VISUAL_GPT_PURE_MODE",
    "visual_hybrid_tone_pipeline": "VISUAL_HYBRID_TONE_PIPELINE",
    "visual_image_backend": "VISUAL_IMAGE_BACKEND",
    "visual_precrop_before_api": "VISUAL_PRECROP_BEFORE_API",
    "visual_disable_pillow_retouch": "VISUAL_DISABLE_PILLOW_RETOUCH",
    "visual_image_quality": "VISUAL_IMAGE_QUALITY",
    "visual_edit_plan_model": "VISUAL_EDIT_PLAN_MODEL",
    "visual_jpeg_export_quality": "VISUAL_JPEG_EXPORT_QUALITY",
}

_PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "visual_produce_mode": "generative",
        "visual_review_enabled": False,
        "visual_edit_plan_enabled": False,
        "visual_edit_prompt_compiler": False,
        "visual_use_ai_image_edit": True,
        "visual_edit_include_kb": True,
        "visual_kb_scope_enabled": True,
        "visual_parallel_copy": True,
        "visual_smart_routing": True,
        "visual_pipeline_trace": True,
        "visual_gpt_pure_mode": False,
        "visual_hybrid_tone_pipeline": False,
        "visual_image_backend": "responses",
        "visual_precrop_before_api": False,
        "visual_disable_pillow_retouch": False,
        "visual_image_quality": "high",
        "visual_jpeg_export_quality": 95,
    },
    "balanced": {
        "visual_produce_mode": "generative",
        "visual_review_enabled": False,
        "visual_edit_plan_enabled": True,
        "visual_edit_prompt_compiler": False,
        "visual_use_ai_image_edit": True,
        "visual_edit_include_kb": True,
        "visual_kb_scope_enabled": True,
        "visual_parallel_copy": True,
        "visual_smart_routing": True,
        "visual_pipeline_trace": True,
        "visual_gpt_pure_mode": False,
        "visual_hybrid_tone_pipeline": False,
        "visual_image_backend": "responses",
        "visual_precrop_before_api": False,
        "visual_disable_pillow_retouch": False,
        "visual_image_quality": "high",
        "visual_jpeg_export_quality": 95,
    },
    "quality": {
        "visual_produce_mode": "generative",
        "visual_review_enabled": False,
        "visual_edit_plan_enabled": True,
        "visual_edit_prompt_compiler": True,
        "visual_use_ai_image_edit": True,
        "visual_edit_include_kb": True,
        "visual_kb_scope_enabled": False,
        "visual_parallel_copy": True,
        "visual_smart_routing": False,
        "visual_pipeline_trace": True,
        "visual_gpt_pure_mode": False,
        "visual_hybrid_tone_pipeline": False,
        "visual_image_backend": "responses",
        "visual_precrop_before_api": True,
        "visual_disable_pillow_retouch": True,
        "visual_image_quality": "high",
        "visual_edit_plan_model": "gpt-4o",
        "visual_jpeg_export_quality": 95,
    },
    "pixel": {
        "visual_produce_mode": "pixel",
        "visual_review_enabled": False,
        "visual_edit_plan_enabled": False,
        "visual_edit_prompt_compiler": False,
        "visual_use_ai_image_edit": False,
        "visual_edit_include_kb": True,
        "visual_kb_scope_enabled": True,
        "visual_parallel_copy": True,
        "visual_smart_routing": False,
        "visual_pipeline_trace": True,
        "visual_gpt_pure_mode": False,
        "visual_hybrid_tone_pipeline": False,
        "visual_image_backend": "responses",
        "visual_precrop_before_api": False,
        "visual_disable_pillow_retouch": False,
        "visual_image_quality": "",
        "visual_jpeg_export_quality": 95,
    },
}


def _env_explicitly_set(env_key: str) -> bool:
    return env_key in os.environ and str(os.environ.get(env_key) or "").strip() != ""


def apply_visual_pipeline_profile(settings: Settings) -> Settings:
    """
    Applica preset da ``visual_pipeline_profile``.

    I valori impostati esplicitamente via env (es. ``VISUAL_EDIT_PLAN_ENABLED``)
    non vengono sovrascritti.
    """
    profile = (settings.visual_pipeline_profile or "").strip().lower()
    if not profile or profile == "custom":
        return settings
    preset = _PROFILE_PRESETS.get(profile)
    if preset is None:
        return settings

    updates: dict[str, Any] = {}
    for field, value in preset.items():
        env_key = _PROFILE_ENV_KEYS.get(field, "")
        if env_key and _env_explicitly_set(env_key):
            continue
        if getattr(settings, field) != value:
            updates[field] = value
    if not updates:
        return settings
    return settings.model_copy(update=updates)
