"""Prompt Visual Review e Visual Producer."""

from __future__ import annotations

from social_automation.brand.loader import (
    build_brand_context_message,
    build_system_message,
    load_story_agent_config,
)
from social_automation.brand.prompt_context import (
    build_produce_user_prompt,
    channels_label,
    format_marketing_objectives_for_prompt,
    image_edit_format_label,
    image_format_label,
    normalize_channels,
    normalize_marketing_objectives,
)
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings, load_settings, repo_root
from social_automation.visual.models import ImageEditPlan

_IMAGE_EDIT_API_PREAMBLE = (
    "EDIT the attached photograph. Do not generate a new image. "
    "Preserve all original pixels and composition.\n\n"
)

_SUBJECT_ARTICLE: dict[str, tuple[str, str]] = {
    "persona": ("la persona", "persona"),
    "volto": ("il volto", "volto"),
    "hamburger": ("l'hamburger", "hamburger"),
    "cibo": ("il cibo", "cibo"),
    "patatine": ("le patatine", "patatine"),
    "hot dog": ("l'hot dog", "hot dog"),
    "panino": ("il panino", "panino"),
}


def _subject_labels(business_category: str | None) -> tuple[str, str]:
    """Etichette soggetto per il prompt di editing (titolo + forma breve)."""
    cat = (business_category or "").strip().lower()
    if cat in {"food", "birra", "beer"}:
        return "l'hamburger", "hamburger"
    if cat in {"boss", "peppe", "staff"}:
        return "la persona", "persona"
    return "il soggetto principale", "soggetto"


def _subject_labels_from_plan(
    plan: ImageEditPlan | None,
    business_category: str | None,
) -> tuple[str, str]:
    """Deriva soggetto dal piano vision; fallback su categoria."""
    if plan is None or not plan.has_content:
        return _subject_labels(business_category)

    if plan.sharpness_targets:
        short = " e ".join(plan.sharpness_targets)
        if len(plan.sharpness_targets) == 1:
            key = plan.sharpness_targets[0].strip().lower()
            if key in _SUBJECT_ARTICLE:
                return _SUBJECT_ARTICLE[key]
            return f"il {key}", key
        return short, short

    if plan.subjects:
        if len(plan.subjects) == 1:
            key = plan.subjects[0].strip().lower()
            if key in _SUBJECT_ARTICLE:
                return _SUBJECT_ARTICLE[key]
            return f"il {key}", key
        short = " e ".join(plan.subjects)
        return short, short

    return _subject_labels(business_category)


def format_edit_plan_for_prompt(
    plan: ImageEditPlan,
    *,
    platform: Platform,
    media_format: MediaFormat,
    hybrid_mode: bool = False,
) -> str:
    """Sezione piano editing foto-specifico (come Custom GPT step 1–7)."""
    fmt = image_edit_format_label(platform=platform, media_format=media_format)
    subjects = ", ".join(plan.subjects) if plan.subjects else "n.d."
    preserve = ", ".join(plan.preserve_elements) if plan.preserve_elements else "n.d."
    sharpness = ", ".join(plan.sharpness_targets) if plan.sharpness_targets else "n.d."
    background = (
        "mantieni morbido/sfocato, senza profondità di campo artificiale"
        if plan.preserve_soft_background
        else "n.d."
    )
    crop = plan.crop_plan or "n.d."
    adjustments = plan.adjustments_notes or "lieve esposizione, ombre e contrasto come da regole"
    la = plan.light_adjustments
    if la.has_tone:
        tone_line = (
            f"exposure={la.exposure:+.3f}, contrast={la.contrast:+.3f}, "
            f"saturation={la.saturation:+.3f} (applicati in post, non dall'AI)"
        )
    else:
        tone_line = adjustments

    lines = [
        "Piano editing per questa foto (analisi preliminare)",
        f"- Soggetti: {subjects}",
        f"- Elementi da preservare: {preserve}",
    ]
    if not hybrid_mode:
        lines.append(f"- Crop: {crop}")
    else:
        lines.append(f"- Crop: già applicato al formato {fmt}")
    lines.extend(
        [
            f"- Nitidezza selettiva su: {sharpness}",
            f"- Sfondo: {background}",
            f"- Regolazioni tono: {tone_line}",
        ]
    )
    if plan.reasoning:
        lines.append(f"- Analisi: {plan.reasoning}")

    if hybrid_mode:
        lines.extend(
            [
                "",
                "Esegui in ordine (solo compiti AI — tono globale già in post):",
                "1. Nitidezza selettiva sui target indicati",
                "2. Micro-contrasto locale sul soggetto",
                "3. Pulizia minima",
                f"4. Export finale {fmt}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Esegui in ordine:",
                "1. Analisi composizione (già fornita sopra)",
                f"2. Crop al formato {fmt}",
                "3. Regolazioni globali leggere",
                "4. Contrasto / micro-contrasto",
                "5. Nitidezza selettiva",
                "6. Pulizia minima",
                f"7. Export finale {fmt}",
            ]
        )
    return "\n".join(lines)


def _load_image_edit_task_template(
    settings: Settings | None = None,
    *,
    hybrid_mode: bool = False,
) -> str:
    s = settings or load_settings()
    if hybrid_mode:
        hybrid_path = s.visual_hybrid_prompt_path
        if hybrid_path.is_file():
            return hybrid_path.read_text(encoding="utf-8").strip()
        fallback = repo_root() / "config/brand/image_edit_hybrid_task_prompt.md"
        if fallback.is_file():
            return fallback.read_text(encoding="utf-8").strip()
    path = s.visual_producer_prompt_path
    if not path.is_file():
        path = repo_root() / "config/brand/image_edit_task_prompt.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _render_image_edit_task_prompt(
    template: str,
    *,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str | None = None,
    channels: list[Platform] | None = None,
    edit_plan: ImageEditPlan | None = None,
) -> str:
    subject, subject_short = _subject_labels_from_plan(edit_plan, business_category)
    fmt = image_edit_format_label(platform=platform, media_format=media_format)
    ch = normalize_channels(channels, fallback_platform=platform)
    out = template
    for key, value in {
        "format": fmt,
        "subject": subject,
        "subject_short": subject_short,
        "channels": channels_label(ch),
    }.items():
        out = out.replace("{" + key + "}", value)
    if edit_plan and edit_plan.preserve_soft_background:
        out += (
            "\n\nImportante: lo sfondo è già sfocato — "
            "non aumentare la profondità di campo artificiale."
        )
    return out.strip()


def build_visual_review_user_prompt(
    *,
    business_category: str | None,
    platform: Platform,
    media_format: MediaFormat,
    content_pillar: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> str:
    objectives = normalize_marketing_objectives(
        marketing_objectives,
        legacy_single=marketing_objective,
    )
    objective = format_marketing_objectives_for_prompt(objectives)
    ch = normalize_channels(channels, fallback_platform=platform)
    return (
        "Modalità Visual Review: valuta se questa foto è già pubblicabile o necessita editing.\n"
        "Rispondi SOLO con JSON valido (nessun markdown):\n"
        "{\n"
        '  "score": 0.0,\n'
        '  "approved": true,\n'
        '  "needs_editing": false,\n'
        '  "reasoning": "breve motivazione in italiano",\n'
        '  "suggested_format": "instagram_4_5|facebook_context|story_9_16"\n'
        "}\n"
        "Regole score (0-10):\n"
        "- score >= 8: foto già pubblicabile, needs_editing=false\n"
        "- score < 8: needs_editing=true\n"
        "- score < 5: approved=false\n"
        f"OBIETTIVO: {objective}\n"
        f"CANALI: {channels_label(ch)}\n"
        f"FORMATO: {image_format_label(platform=platform, media_format=media_format)}\n"
        f"Categoria: {business_category or 'non specificata'}\n"
        f"Content pillar: {content_pillar}\n"
    )


def build_visual_producer_user_prompt(
    *,
    review: dict,
    business_category: str | None,
    platform: Platform,
    media_format: MediaFormat,
    content_pillar: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    settings: Settings | None = None,
    include_extras: bool = True,
) -> str:
    cfg = load_story_agent_config()
    objectives = normalize_marketing_objectives(
        marketing_objectives,
        legacy_single=marketing_objective,
    )
    reasoning = str(review.get("reasoning") or "").strip()
    suggested = str(review.get("suggested_format") or "").strip()
    return build_produce_user_prompt(
        cfg,
        marketing_objective=format_marketing_objectives_for_prompt(objectives),
        channels=normalize_channels(channels, fallback_platform=platform),
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        content_pillar=content_pillar,
        review_notes=reasoning,
        suggested_crop=suggested,
        include_extras=include_extras,
    )


def build_image_edit_instructions(settings: Settings | None = None) -> str:
    """Instructions API: vuote di default (flusso GPT = solo prompt utente + foto)."""
    s = settings or load_settings()
    if not s.visual_edit_include_kb:
        return ""
    return build_system_message(load_story_agent_config())


def build_image_edit_user_prompt(
    *,
    review: dict,
    business_category: str | None,
    platform: Platform,
    media_format: MediaFormat,
    content_pillar: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    settings: Settings | None = None,
    edit_plan: ImageEditPlan | None = None,
    hybrid_mode: bool | None = None,
) -> str:
    """Task editing immagine post-selezione (template dedicato, no /produce)."""
    s = settings or load_settings()
    use_hybrid = (
        bool(s.visual_hybrid_tone_pipeline) if hybrid_mode is None else hybrid_mode
    )
    template = _load_image_edit_task_template(s, hybrid_mode=use_hybrid)
    if template:
        body = _render_image_edit_task_prompt(
            template,
            platform=platform,
            media_format=media_format,
            business_category=business_category,
            channels=channels,
            edit_plan=edit_plan,
        )
        parts = [_IMAGE_EDIT_API_PREAMBLE + body]
        if edit_plan and edit_plan.has_content:
            parts.append(
                format_edit_plan_for_prompt(
                    edit_plan,
                    platform=platform,
                    media_format=media_format,
                    hybrid_mode=use_hybrid,
                )
            )
        return "\n\n".join(parts)
    return build_visual_producer_user_prompt(
        review=review,
        business_category=business_category,
        platform=platform,
        media_format=media_format,
        content_pillar=content_pillar,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
        include_extras=False,
    )


def build_image_edit_prompt(
    *,
    review: dict,
    business_category: str | None,
    platform: Platform,
    media_format: MediaFormat,
    content_pillar: str,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    edit_plan: ImageEditPlan | None = None,
) -> str:
    """
    Prompt legacy per ``/images/edits``: KB inline + /produce.

    Preferire Responses API con ``build_image_edit_instructions`` + ``build_image_edit_user_prompt``.
    """
    cfg = load_story_agent_config()
    task = build_image_edit_user_prompt(
        review=review,
        business_category=business_category,
        platform=platform,
        media_format=media_format,
        content_pillar=content_pillar,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
        edit_plan=edit_plan,
    )
    parts: list[str] = []
    if cfg.business_rules_text.strip():
        parts.append("--- KNOWLEDGE BASE (Story Food & Drink) ---\n\n")
        parts.append(cfg.business_rules_text.strip())
        parts.append("\n\n")
    parts.append(task.strip())
    return "".join(parts).strip()


def build_visual_review_system_message(settings: Settings | None = None) -> str:
    return build_brand_context_message(load_story_agent_config())
