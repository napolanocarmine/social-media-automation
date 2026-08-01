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
from social_automation.visual.pipeline_trace import (
    end_pipeline_trace,
    get_pipeline_trace,
    start_pipeline_trace,
)
from social_automation.visual.postprocess import (
    copy_or_finalize_for_crop_mode,
    precrop_source_for_api,
    resize_only_to_target_size,
)
from social_automation.visual.prompt_compiler import compile_image_edit_prompt
from social_automation.visual.prompts import (
    build_image_edit_instructions,
    build_image_edit_prompt,
    build_image_edit_user_prompt,
)
from social_automation.visual.review import decision_engine, run_visual_review
from social_automation.visual.routing import (
    resolve_produce_mode,
    should_run_edit_plan,
    should_run_prompt_compiler,
)

_LOG = logging.getLogger(__name__)

# Default tono conservativo se il piano vision non restituisce numeri (≈ +0.2 EV GPT).
_DEFAULT_HYBRID_TONE = LightAdjustments(exposure=0.08, contrast=0.04)


@dataclass(frozen=True)
class _EditPipelineFlags:
    gpt_pure: bool
    precrop: bool
    hybrid: bool
    skip_post_crop: bool


def _edit_pipeline_flags(settings: Settings) -> _EditPipelineFlags:
    pure = bool(settings.visual_gpt_pure_mode)
    return _EditPipelineFlags(
        gpt_pure=pure,
        precrop=bool(settings.visual_precrop_before_api) and not pure,
        hybrid=bool(settings.visual_hybrid_tone_pipeline) and not pure,
        skip_post_crop=bool(settings.visual_skip_post_crop) or pure,
    )


@dataclass(frozen=True)
class _ProducePlan:
    use_original: bool
    use_generative: bool
    use_pixel: bool
    use_pillow_only: bool


def _build_produce_plan(
    settings: Settings,
    review: VisualReview,
    decision: VisualDecision | None,
) -> _ProducePlan:
    ai_edit_ready = settings.visual_use_ai_image_edit and image_edit_configured(settings)
    produce_mode = resolve_produce_mode(settings)

    if decision is None:
        use_original = False
        use_generative = (
            produce_mode == "generative"
            and settings.visual_use_ai_image_edit
            and ai_edit_ready
        )
        use_pixel = produce_mode == "pixel" or not settings.visual_use_ai_image_edit
        use_pillow_only = False
    else:
        use_original = decision.use_original
        use_generative = (
            settings.visual_use_ai_image_edit
            and ai_edit_ready
            and decision.needs_ai_editing
            and not decision.use_original
            and produce_mode == "generative"
        )
        use_pixel = (
            decision.needs_ai_editing
            and not decision.use_original
            and (produce_mode == "pixel" or not settings.visual_use_ai_image_edit)
        )
        use_pillow_only = not use_original and not use_generative and not use_pixel

    return _ProducePlan(
        use_original=use_original,
        use_generative=use_generative,
        use_pixel=use_pixel,
        use_pillow_only=use_pillow_only,
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
    allow_center_crop: bool = True,
) -> Path:
    return copy_or_finalize_for_crop_mode(
        source_path,
        dest_path,
        crop_mode,
        jpeg_quality=jpeg_quality,
        allow_center_crop=allow_center_crop,
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
    run_edit_plan = should_run_edit_plan(
        settings,
        business_category=business_category,
        review=review,
    )
    trace = get_pipeline_trace()
    if run_edit_plan:
        def _plan_step() -> ImageEditPlan:
            return run_image_edit_plan(
                source_path,
                settings=settings,
                business_category=business_category,
                platform=platform,
                media_format=media_format,
                channels=channels,
            )

        try:
            if trace is not None:
                edit_plan = trace.run("edit_plan", _plan_step)
            else:
                edit_plan = _plan_step()
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
    elif trace is not None:
        trace.skip("edit_plan", reason="routing or disabled")
    elif pipeline.gpt_pure:
        pass
    else:
        _LOG.debug("Edit plan skipped (smart routing or disabled)")

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
        if should_run_prompt_compiler(settings):
            user_prompt = compile_image_edit_prompt(
                user_prompt,
                settings=settings,
                edit_plan=edit_plan,
            )
        elif trace is not None:
            trace.skip("prompt_compiler", reason="disabled")
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
        def _image_edit_step() -> ImageEditApiResult:
            return run_image_edit(
                api_source,
                instructions=instructions,
                user_prompt=user_prompt,
                legacy_prompt=legacy_prompt,
                dest_path=api_dest,
                settings=settings,
                crop_mode=crop_mode,
                jpeg_quality=jpeg_q,
            )

        if trace is not None:
            api_result = trace.run("image_edit", _image_edit_step, backend=settings.visual_image_backend)
        else:
            api_result = _image_edit_step()
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

    story_no_center_crop = media_format == MediaFormat.STORY
    if skip_post_crop:
        if story_no_center_crop:
            after_resize = resize_only_to_target_size(
                api_dest,
                final_path,
                crop_mode,
                jpeg_quality=jpeg_q,
            )
        else:
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
            allow_center_crop=not story_no_center_crop,
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


def _run_pillow_produce(
    source_path: Path,
    dest_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    crop_mode: str,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    method: str = "produce_pixel",
) -> tuple[Path, dict[str, Any], str]:
    trace = get_pipeline_trace()

    def _retouch() -> dict[str, Any]:
        return run_retouch_analysis(
            source_path,
            settings=settings,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            marketing_objective=marketing_objective,
            channels=channels,
        )

    if trace is not None:
        retouch_json = trace.run("retouch_analysis", _retouch)
    else:
        retouch_json = _retouch()
    final_path = _export_with_pillow(
        source_path,
        dest_path,
        platform=platform,
        media_format=media_format,
        crop_mode=crop_mode,
        retouch_data=retouch_json,
    )
    return final_path, retouch_json, method


def _run_generative_with_fallback(
    source_path: Path,
    dest_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    crop_mode: str,
    review: VisualReview,
    force_ai_edit: bool,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> tuple[Path, Path | None, str, dict[str, Any] | None, str, dict[str, Any] | None]:
    producer_notes = review.reasoning
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
        return final_path, generated_path, method, edit_plan_json, producer_notes, None
    except Exception as exc:
        if force_ai_edit:
            raise RuntimeError(f"Image edit AI fallito: {exc}") from exc
        _LOG.warning("AI edit fallito, fallback Pillow: %s", exc)
        producer_notes = f"{review.reasoning} | AI fallback: {exc}"
        final_path, retouch_json, method = _run_pillow_produce(
            source_path,
            dest_path,
            settings=settings,
            platform=platform,
            media_format=media_format,
            business_category=business_category,
            crop_mode=crop_mode,
            marketing_objective=marketing_objective,
            channels=channels,
            method="pillow_fallback",
        )
        return final_path, None, method, None, producer_notes, retouch_json


def _produce_asset(
    source_path: Path,
    *,
    settings: Settings,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    file_id: str,
    review: VisualReview,
    decision: VisualDecision | None = None,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> VisualProductionResult:
    """Pipeline unificata: GPT direct (decision=None) o Visual Review."""
    crop_mode = (
        _normalize_crop_mode(review.suggested_format, platform=platform, media_format=media_format)
        if decision is not None
        else crop_mode_for_platform(platform, media_format)
    )
    dest_path = _dest_path(
        settings.output_dir,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
    )
    plan = _build_produce_plan(settings, review, decision)
    force_ai_edit = bool(
        settings.visual_use_ai_image_edit and settings.visual_disable_pillow_retouch
    )
    ai_edit_ready = settings.visual_use_ai_image_edit and image_edit_configured(settings)

    if force_ai_edit and not ai_edit_ready and (plan.use_generative or decision is None):
        raise RuntimeError(
            "VISUAL_DISABLE_PILLOW_RETOUCH attivo ma image edit non configurato "
            "(VISION_API_KEY e VISUAL_RESPONSES_MODEL richiesti)"
        )

    generated_path: Path | None = None
    retouch_json: dict[str, Any] | None = None
    edit_plan_json: dict[str, Any] | None = None
    method = "original"
    producer_notes = review.reasoning
    status = decision.visual_status if decision else "ai_editing"

    if plan.use_original:
        final_path = _export_crop_only(source_path, dest_path, crop_mode=crop_mode)
        method = "original"
        if decision and decision.needs_manual_review:
            status = "manual_review"
    elif plan.use_generative:
        final_path, generated_path, method, edit_plan_json, producer_notes, retouch_json = (
            _run_generative_with_fallback(
                source_path,
                dest_path,
                settings=settings,
                platform=platform,
                media_format=media_format,
                business_category=business_category,
                file_id=file_id,
                crop_mode=crop_mode,
                review=review,
                force_ai_edit=force_ai_edit,
                marketing_objectives=marketing_objectives,
                marketing_objective=marketing_objective,
                channels=channels,
            )
        )
        if decision and method == "pillow_fallback":
            decision = VisualDecision(
                use_original=False,
                needs_ai_editing=False,
                needs_manual_review=decision.needs_manual_review,
                visual_status="pillow_fallback",
            )
            status = "pillow_fallback"
        elif force_ai_edit and method in {"ai_edited", "ai_edited_hybrid", "ai_edited_pure"}:
            status = "ai_editing"
    elif plan.use_pixel:
        final_path, retouch_json, method = _run_pillow_produce(
            source_path,
            dest_path,
            settings=settings,
            platform=platform,
            media_format=media_format,
            business_category=business_category,
            crop_mode=crop_mode,
            marketing_objective=marketing_objective,
            channels=channels,
            method="produce_pixel",
        )
    elif plan.use_pillow_only:
        if settings.visual_disable_pillow_retouch:
            raise RuntimeError(
                "VISUAL_DISABLE_PILLOW_RETOUCH attivo ma il path AI non è disponibile "
                f"(score={review.score}, needs_editing={review.needs_editing})"
            )
        pillow_method = "pillow_fallback" if (decision and decision.needs_ai_editing) else "pillow"
        final_path, retouch_json, method = _run_pillow_produce(
            source_path,
            dest_path,
            settings=settings,
            platform=platform,
            media_format=media_format,
            business_category=business_category,
            crop_mode=crop_mode,
            marketing_objective=marketing_objective,
            channels=channels,
            method=pillow_method,
        )
    elif decision is None:
        raise RuntimeError(
            "Edit AI non configurato. Imposta VISUAL_USE_AI_IMAGE_EDIT=true e "
            "VISUAL_RESPONSES_MODEL, oppure VISUAL_PRODUCE_MODE=pixel."
        )
    else:
        raise RuntimeError(
            "Nessun path di produzione disponibile per la foto "
            f"(score={review.score}, needs_editing={review.needs_editing})"
        )

    if decision is None:
        visual_status = (
            "ai_editing"
            if method in {"ai_edited", "ai_edited_hybrid", "ai_edited_pure"}
            else method
        )
    else:
        visual_status = status
        if decision.needs_manual_review and visual_status == "original":
            visual_status = "manual_review"

    trace = get_pipeline_trace()
    trace_json = trace.to_dict() if trace is not None else None
    if edit_plan_json is None and trace_json:
        edit_plan_json = {"pipeline_trace": trace_json}
    elif trace_json:
        edit_plan_json = {**edit_plan_json, "pipeline_trace": trace_json}

    return VisualProductionResult(
        final_path=str(final_path),
        original_path=str(source_path),
        generated_image_path=str(generated_path) if generated_path else None,
        visual_score=review.score,
        visual_status=visual_status,
        editing_required=not plan.use_original,
        method=method,
        review=review,
        retouch_json=retouch_json,
        producer_notes=producer_notes,
        edit_plan_json=edit_plan_json,
    )


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
    return _produce_asset(
        source_path,
        settings=settings,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
        review=review,
        decision=None,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
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
    trace = get_pipeline_trace()

    def _review_step() -> VisualReview:
        return run_visual_review(
            source_path,
            settings=settings,
            business_category=business_category,
            platform=platform,
            media_format=media_format,
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
            channels=channels,
        )

    if trace is not None:
        review = trace.run("visual_review", _review_step)
    else:
        review = _review_step()
    decision = decision_engine(review, settings=settings)
    return _produce_asset(
        source_path,
        settings=settings,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        file_id=file_id,
        review=review,
        decision=decision,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
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
    trace: Any = None
    if settings.visual_pipeline_trace:
        trace = start_pipeline_trace(photo_id=file_id)
    try:
        if settings.visual_review_enabled:
            result = _produce_with_visual_review(
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
        else:
            result = _produce_gpt_direct(
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
        return result
    finally:
        if trace is not None:
            end_pipeline_trace(log=settings.visual_pipeline_trace)
