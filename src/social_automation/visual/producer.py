"""Orchestrazione Visual Producer: flusso GPT diretto o legacy con Visual Review."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from social_automation.brand.agent import run_retouch_analysis
from social_automation.brand.loader import pillar_for_category
from social_automation.models import MediaFormat, Platform
from social_automation.processing.image_adjust import (
    apply_retouch_to_file,
    apply_tone_to_file,
    crop_mode_for_platform,
)
from social_automation.settings import Settings
from social_automation.visual.edit_plan import run_image_edit_plan
from social_automation.visual.image_edit import image_edit_configured, run_image_edit
from social_automation.visual.models import (
    ImageEditApiResult,
    ImageEditPlan,
    LightAdjustments,
    VisualDecision,
    VisualProductionResult,
    VisualReview,
)
from social_automation.visual.postprocess import (
    copy_or_finalize_for_crop_mode,
    precrop_source_for_api,
)
from social_automation.visual.prompt_compiler import compile_image_edit_prompt
from social_automation.visual.prompts import (
    build_image_edit_instructions,
    build_image_edit_prompt,
    build_image_edit_user_prompt,
)
from social_automation.visual.review import decision_engine, run_visual_review

_LOG = logging.getLogger(__name__)

# Default tono conservativo se il piano vision non restituisce numeri (≈ +0.2 EV GPT).
_DEFAULT_HYBRID_TONE = LightAdjustments(exposure=0.08, contrast=0.04)


@dataclass(frozen=True)
class _EditPipelineFlags:
    gpt_pure: bool
    edit_plan: bool
    precrop: bool
    hybrid: bool
    compiler: bool
    skip_post_crop: bool


def _edit_pipeline_flags(settings: Settings) -> _EditPipelineFlags:
    pure = bool(settings.visual_gpt_pure_mode)
    return _EditPipelineFlags(
        gpt_pure=pure,
        edit_plan=bool(settings.visual_edit_plan_enabled) and not pure,
        precrop=bool(settings.visual_precrop_before_api) and not pure,
        hybrid=bool(settings.visual_hybrid_tone_pipeline) and not pure,
        compiler=bool(settings.visual_edit_prompt_compiler) and not pure,
        skip_post_crop=bool(settings.visual_skip_post_crop) or pure,
    )


def _effective_tone_adjustments(
    edit_plan: ImageEditPlan | None,
    *,
    hybrid: bool,
) -> dict[str, float] | None:
    if not hybrid:
        return None
    if edit_plan is not None and edit_plan.light_adjustments.has_tone:
        return edit_plan.light_adjustments.to_dict()
    if edit_plan is not None and edit_plan.has_content:
        return _DEFAULT_HYBRID_TONE.to_dict()
    if hybrid:
        return _DEFAULT_HYBRID_TONE.to_dict()
    return None


def _apply_hybrid_tone(
    source: Path,
    dest: Path,
    tone: dict[str, float],
    *,
    jpeg_quality: int,
) -> Path:
    tone_only = {
        k: tone[k]
        for k in ("exposure", "contrast", "saturation")
        if k in tone
    }
    if not any(abs(v) > 0.001 for v in tone_only.values()):
        if source != dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        return dest
    _LOG.info(
        "Hybrid tone Pillow: exposure=%+.3f contrast=%+.3f saturation=%+.3f",
        tone_only.get("exposure", 0.0),
        tone_only.get("contrast", 0.0),
        tone_only.get("saturation", 0.0),
    )
    return apply_tone_to_file(
        source,
        dest,
        tone_only,
        jpeg_quality=jpeg_quality,
    )


def _normalize_crop_mode(raw: str, *, platform: Platform, media_format: MediaFormat) -> str:
    val = (raw or "").strip().lower()
    allowed = {
        "none",
        "instagram_4_5",
        "instagram_post",
        "facebook_context",
        "facebook_post",
        "story_9_16",
        "instagram_story",
    }
    if val in allowed:
        return val
    return crop_mode_for_platform(platform, media_format)


def _dest_path(
    output_dir: Path,
    *,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    suffix: str = "",
) -> Path:
    base = output_dir / "processed"
    if media_format == MediaFormat.STORY:
        sub = base / "stories"
    elif platform == Platform.FACEBOOK:
        sub = base / "fb"
    else:
        sub = base / "ig"
    stem = f"{business_category}_{file_id}{suffix}"
    if media_format == MediaFormat.STORY:
        stem = f"{stem}_story"
    return sub / f"{stem}.jpg"


def _export_crop_only(
    source_path: Path,
    dest_path: Path,
    *,
    crop_mode: str,
    jpeg_quality: int = 95,
) -> Path:
    return copy_or_finalize_for_crop_mode(
        source_path,
        dest_path,
        crop_mode,
        jpeg_quality=jpeg_quality,
    )


def _export_with_pillow(
    source_path: Path,
    dest_path: Path,
    *,
    platform: Platform,
    media_format: MediaFormat,
    crop_mode: str,
    retouch_data: dict[str, Any] | None = None,
) -> Path:
    adjustments: dict[str, Any] = {"crop_mode": crop_mode}
    if retouch_data and isinstance(retouch_data.get("light_adjustments"), dict):
        adjustments = dict(retouch_data["light_adjustments"])
        adjustments.setdefault("crop_mode", crop_mode)
    else:
        adjustments.update(
            {
                "exposure": 0.0,
                "contrast": 0.0,
                "sharpness": 0.0,
                "saturation": 0.0,
            }
        )
    fallback = crop_mode_for_platform(platform, media_format)
    return apply_retouch_to_file(
        source_path,
        dest_path,
        adjustments,
        fallback_crop=fallback,
    )


def _gpt_stub_review(*, platform: Platform, media_format: MediaFormat) -> VisualReview:
    crop = crop_mode_for_platform(platform, media_format)
    return VisualReview(
        score=0.0,
        approved=True,
        needs_editing=True,
        reasoning="Flusso GPT diretto (Visual Review disabilitata)",
        suggested_format=crop,
    )


def _run_ai_image_edit(
    source_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    crop_mode: str,
    review: VisualReview | None = None,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> tuple[Path, Path | None, str, dict[str, Any] | None, str]:
    """
    Edit immagine: prompt task + foto (come Custom GPT).

    Se ``visual_skip_post_crop`` è true, l'output API è il file finale (crop nel prompt).
    """
    final_path = _dest_path(
        settings.output_dir,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
    )
    pipeline = _edit_pipeline_flags(settings)
    skip_post_crop = pipeline.skip_post_crop
    if pipeline.gpt_pure:
        _LOG.info(
            "GPT pure mode: originale → Responses API → output diretto (no pre-crop/hybrid/compiler)"
        )
    api_dest = final_path if skip_post_crop else _dest_path(
        settings.output_dir,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
        suffix="_gen",
    )
    review_payload = {
        "reasoning": (review.reasoning if review else ""),
        "suggested_format": (review.suggested_format if review else crop_mode),
    }
    edit_plan = None
    edit_plan_notes = ""
    hybrid = pipeline.hybrid
    if pipeline.edit_plan:
        try:
            edit_plan = run_image_edit_plan(
                source_path,
                settings=settings,
                business_category=business_category,
                platform=platform,
                media_format=media_format,
                channels=channels,
            )
            if edit_plan.has_content:
                edit_plan_notes = edit_plan.reasoning or "piano editing generato"
                la = edit_plan.light_adjustments
                _LOG.info(
                    "Image edit plan: subjects=%s sharpness=%s crop=%s tone=(%+.3f,%+.3f)",
                    list(edit_plan.subjects),
                    list(edit_plan.sharpness_targets),
                    (edit_plan.crop_plan or "")[:120],
                    la.exposure,
                    la.contrast,
                )
        except Exception as exc:
            _LOG.warning("Image edit plan fallito, proseguo senza piano: %s", exc)
            edit_plan_notes = f"edit plan fallback: {exc}"

    tone_adjustments = _effective_tone_adjustments(edit_plan, hybrid=hybrid)

    api_source = source_path
    precrop_path: Path | None = None
    jpeg_q = int(settings.visual_jpeg_export_quality)
    api_result: ImageEditApiResult | None = None
    try:
        if pipeline.precrop:
            precrop_path = _dest_path(
                settings.output_dir,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
                suffix="_precrop",
            )
            precrop_source_for_api(
                source_path,
                precrop_path,
                crop_mode,
                jpeg_quality=jpeg_q,
            )
            api_source = precrop_path

        instructions = build_image_edit_instructions(settings)
        user_prompt = build_image_edit_user_prompt(
            review=review_payload,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            content_pillar=pillar_for_category(business_category),
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
            channels=channels,
            settings=settings,
            edit_plan=edit_plan,
            hybrid_mode=hybrid,
        )
        if pipeline.compiler:
            user_prompt = compile_image_edit_prompt(
                user_prompt,
                settings=settings,
                edit_plan=edit_plan,
            )
        legacy_prompt = build_image_edit_prompt(
            review=review_payload,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            content_pillar=pillar_for_category(business_category),
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
            channels=channels,
            edit_plan=edit_plan,
        )
        api_result = run_image_edit(
            api_source,
            instructions=instructions,
            user_prompt=user_prompt,
            legacy_prompt=legacy_prompt,
            dest_path=api_dest,
            settings=settings,
            crop_mode=crop_mode,
            jpeg_quality=jpeg_q,
        )
    finally:
        if precrop_path is not None and precrop_path.is_file():
            precrop_path.unlink(missing_ok=True)

    generated_path: Path | None = None
    if pipeline.gpt_pure:
        method = "ai_edited_pure"
    elif hybrid:
        method = "ai_edited_hybrid"
    else:
        method = "ai_edited"

    if skip_post_crop:
        after_resize = api_dest
    else:
        generated_path = api_dest
        resize_dest = final_path
        if hybrid and tone_adjustments:
            resize_dest = _dest_path(
                settings.output_dir,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
                suffix="_sized",
            )
        after_resize = _export_crop_only(
            api_dest,
            resize_dest,
            crop_mode=crop_mode,
            jpeg_quality=jpeg_q,
        )

    if hybrid and tone_adjustments:
        out_final = _apply_hybrid_tone(
            after_resize,
            final_path,
            tone_adjustments,
            jpeg_quality=jpeg_q,
        )
        if (
            after_resize != api_dest
            and after_resize != out_final
            and after_resize.is_file()
        ):
            after_resize.unlink(missing_ok=True)
    else:
        out_final = after_resize

    plan_json: dict[str, Any] | None = None
    if edit_plan and edit_plan.has_content:
        plan_json = edit_plan.to_dict()
    meta: dict[str, Any] = {}
    if pipeline.gpt_pure:
        meta["mode"] = "gpt_pure"
    if api_result and api_result.revised_prompt:
        meta["revised_prompt"] = api_result.revised_prompt
    if meta:
        plan_json = {**(plan_json or {}), **meta}
    return out_final, generated_path, method, plan_json, edit_plan_notes


def _produce_gpt_direct(
    source_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> VisualProductionResult:
    """Foto selezionata → prompt editing → API (senza Visual Review)."""
    review = _gpt_stub_review(platform=platform, media_format=media_format)
    crop_mode = crop_mode_for_platform(platform, media_format)
    produce_mode = (settings.visual_produce_mode or "generative").strip().lower()
    ai_edit_ready = settings.visual_use_ai_image_edit and image_edit_configured(settings)
    force_ai_edit = bool(
        settings.visual_use_ai_image_edit and settings.visual_disable_pillow_retouch
    )

    if force_ai_edit and not ai_edit_ready:
        raise RuntimeError(
            "VISUAL_DISABLE_PILLOW_RETOUCH attivo ma image edit non configurato "
            "(VISION_API_KEY e VISUAL_RESPONSES_MODEL richiesti)"
        )

    generated_path: Path | None = None
    retouch_json: dict[str, Any] | None = None
    edit_plan_json: dict[str, Any] | None = None
    method = "original"
    producer_notes = review.reasoning

    if produce_mode == "generative" and settings.visual_use_ai_image_edit and ai_edit_ready:
        try:
            final_path, generated_path, method, edit_plan_json, plan_notes = _run_ai_image_edit(
                source_path,
                settings=settings,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
                crop_mode=crop_mode,
                review=review,
                marketing_objectives=marketing_objectives,
                marketing_objective=marketing_objective,
                channels=channels,
            )
            if plan_notes:
                producer_notes = f"{review.reasoning} | {plan_notes}"
        except Exception as exc:
            if force_ai_edit:
                raise RuntimeError(f"Image edit AI fallito: {exc}") from exc
            _LOG.warning("GPT direct edit fallito, fallback Pillow: %s", exc)
            producer_notes = f"{review.reasoning} | AI fallback: {exc}"
            retouch_json = run_retouch_analysis(
                source_path,
                settings=settings,
                business_category=business_category,
                platform=platform,
                media_format=media_format,
                marketing_objective=marketing_objective,
                channels=channels,
            )
            final_path = _export_with_pillow(
                source_path,
                _dest_path(
                    settings.output_dir,
                    platform=platform,
                    media_format=media_format,
                    business_category=business_category,
                    file_id=file_id,
                ),
                platform=platform,
                media_format=media_format,
                crop_mode=crop_mode,
                retouch_data=retouch_json,
            )
            method = "pillow_fallback"
    elif produce_mode == "pixel" or not settings.visual_use_ai_image_edit:
        retouch_json = run_retouch_analysis(
            source_path,
            settings=settings,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            marketing_objective=marketing_objective,
            channels=channels,
        )
        final_path = _export_with_pillow(
            source_path,
            _dest_path(
                settings.output_dir,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
            ),
            platform=platform,
            media_format=media_format,
            crop_mode=crop_mode,
            retouch_data=retouch_json,
        )
        method = "produce_pixel"
    else:
        raise RuntimeError(
            "Edit AI non configurato. Imposta VISUAL_USE_AI_IMAGE_EDIT=true e "
            "VISUAL_RESPONSES_MODEL, oppure VISUAL_PRODUCE_MODE=pixel."
        )

    return VisualProductionResult(
        final_path=str(final_path),
        original_path=str(source_path),
        generated_image_path=str(generated_path) if generated_path else None,
        visual_score=review.score,
        visual_status="ai_editing" if method in {"ai_edited", "ai_edited_hybrid", "ai_edited_pure"} else method,
        editing_required=True,
        method=method,
        review=review,
        retouch_json=retouch_json,
        producer_notes=producer_notes,
        edit_plan_json=edit_plan_json,
    )


def _produce_with_visual_review(
    source_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> VisualProductionResult:
    """Pipeline legacy: Visual Review → decision → edit / originale / Pillow."""
    review = run_visual_review(
        source_path,
        settings=settings,
        business_category=business_category,
        platform=platform,
        media_format=media_format,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
    decision = decision_engine(review, settings=settings)
    crop_mode = _normalize_crop_mode(review.suggested_format, platform=platform, media_format=media_format)
    final_path = _dest_path(
        settings.output_dir,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
    )
    generated_path: Path | None = None
    retouch_json: dict[str, Any] | None = None
    edit_plan_json: dict[str, Any] | None = None
    method = "original"
    producer_notes = review.reasoning

    force_ai_edit = bool(
        settings.visual_use_ai_image_edit and settings.visual_disable_pillow_retouch
    )
    ai_edit_ready = settings.visual_use_ai_image_edit and image_edit_configured(settings)
    produce_mode = (settings.visual_produce_mode or "generative").strip().lower()
    use_original_path = decision.use_original
    use_generative_produce = (
        settings.visual_use_ai_image_edit
        and ai_edit_ready
        and decision.needs_ai_editing
        and not decision.use_original
        and produce_mode == "generative"
    )
    use_pixel_produce = (
        decision.needs_ai_editing
        and not decision.use_original
        and (produce_mode == "pixel" or not settings.visual_use_ai_image_edit)
    )

    if force_ai_edit and not ai_edit_ready:
        raise RuntimeError(
            "VISUAL_DISABLE_PILLOW_RETOUCH attivo ma image edit non configurato "
            "(VISION_API_KEY e VISUAL_IMAGE_MODEL richiesti)"
        )

    if use_original_path:
        final_path = _export_crop_only(source_path, final_path, crop_mode=crop_mode)
        method = "original"
    elif use_generative_produce:
        try:
            final_path, generated_path, method, edit_plan_json, plan_notes = _run_ai_image_edit(
                source_path,
                settings=settings,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
                crop_mode=crop_mode,
                review=review,
                marketing_objectives=marketing_objectives,
                marketing_objective=marketing_objective,
                channels=channels,
            )
            if plan_notes:
                producer_notes = f"{review.reasoning} | {plan_notes}"
        except Exception as exc:
            if force_ai_edit:
                raise RuntimeError(f"Image edit AI fallito: {exc}") from exc
            _LOG.warning("Visual Producer AI fallito, fallback Pillow: %s", exc)
            producer_notes = f"{review.reasoning} | AI fallback: {exc}"
            retouch_json = run_retouch_analysis(
                source_path,
                settings=settings,
                business_category=business_category,
                platform=platform,
                media_format=media_format,
                marketing_objective=marketing_objective,
                channels=channels,
            )
            final_path = _export_with_pillow(
                source_path,
                final_path,
                platform=platform,
                media_format=media_format,
                crop_mode=crop_mode,
                retouch_data=retouch_json,
            )
            method = "pillow_fallback"
            decision = VisualDecision(
                use_original=False,
                needs_ai_editing=False,
                needs_manual_review=decision.needs_manual_review,
                visual_status="pillow_fallback",
            )
    elif use_pixel_produce:
        retouch_json = run_retouch_analysis(
            source_path,
            settings=settings,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            marketing_objective=marketing_objective,
            channels=channels,
        )
        final_path = _export_with_pillow(
            source_path,
            final_path,
            platform=platform,
            media_format=media_format,
            crop_mode=crop_mode,
            retouch_data=retouch_json,
        )
        method = "produce_pixel"
    elif settings.visual_disable_pillow_retouch:
        raise RuntimeError(
            "VISUAL_DISABLE_PILLOW_RETOUCH attivo ma il path AI non è disponibile "
            f"(score={review.score}, needs_editing={review.needs_editing})"
        )
    else:
        retouch_json = run_retouch_analysis(
            source_path,
            settings=settings,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            marketing_objective=marketing_objective,
            channels=channels,
        )
        final_path = _export_with_pillow(
            source_path,
            final_path,
            platform=platform,
            media_format=media_format,
            crop_mode=crop_mode,
            retouch_data=retouch_json,
        )
        method = "pillow_fallback" if decision.needs_ai_editing else "pillow"

    status = decision.visual_status
    if force_ai_edit and method in {"ai_edited", "ai_edited_hybrid", "ai_edited_pure"}:
        status = "ai_editing"
    if decision.needs_manual_review and status == "original":
        status = "manual_review"

    return VisualProductionResult(
        final_path=str(final_path),
        original_path=str(source_path),
        generated_image_path=str(generated_path) if generated_path else None,
        visual_score=review.score,
        visual_status=status,
        editing_required=not use_original_path,
        method=method,
        review=review,
        retouch_json=retouch_json,
        producer_notes=producer_notes,
        edit_plan_json=edit_plan_json,
    )


def produce_final_asset(
    source_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str | None,
    file_id: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> VisualProductionResult:
    biz = (business_category or "photo").strip().lower()
    if settings.visual_review_enabled:
        return _produce_with_visual_review(
            source_path,
            settings=settings,
            platform=platform,
            media_format=media_format,
            business_category=biz,
            file_id=file_id,
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
            channels=channels,
        )
    return _produce_gpt_direct(
        source_path,
        settings=settings,
        platform=platform,
        media_format=media_format,
        business_category=biz,
        file_id=file_id,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
