"""Vision pre-edit: piano editing foto-specifico (parità Custom GPT)."""

from __future__ import annotations

from pathlib import Path

from social_automation.brand.loader import build_system_message, load_story_agent_config, pillar_for_category
from social_automation.brand.openai_json import api_configured, chat_vision_json
from social_automation.brand.prompt_context import channels_label, image_edit_format_label, normalize_channels
from social_automation.models import MediaFormat, Platform
from social_automation.settings import Settings
from social_automation.visual.models import ImageEditPlan


def build_image_edit_plan_user_prompt(
    *,
    business_category: str | None,
    platform: Platform,
    media_format: MediaFormat,
    content_pillar: str,
    channels: list[Platform] | None = None,
) -> str:
    ch = normalize_channels(channels, fallback_platform=platform)
    fmt = image_edit_format_label(platform=platform, media_format=media_format)
    return (
        "Modalità Image Edit Plan: analizza la foto e produci un piano di editing fotografico "
        "conservativo per il formato social indicato.\n"
        "NON valutare se la foto è pubblicabile (niente score). "
        "NON generare copy. Rispondi SOLO con JSON valido (nessun markdown):\n"
        "{\n"
        '  "subjects": ["soggetto principale", "..."],\n'
        '  "preserve_elements": ["logo", "bandierina", "patatine", "..."],\n'
        '  "crop_plan": "istruzioni crop specifiche per questa foto e il formato target",\n'
        '  "sharpness_targets": ["volto", "cibo"],\n'
        '  "preserve_soft_background": true,\n'
        '  "adjustments_notes": "breve descrizione in italiano delle regolazioni",\n'
        '  "light_adjustments": {\n'
        '    "exposure": 0.08,\n'
        '    "contrast": 0.04,\n'
        '    "saturation": 0.0,\n'
        '    "sharpness": 0.0\n'
        "  },\n"
        '  "reasoning": "breve sintesi analisi in italiano"\n'
        "}\n"
        "Regole:\n"
        "- Priorità crop (KB §16): persone > momenti condivisi > Peppe > food > ambiente\n"
        "- crop_plan deve essere specifico per QUESTA foto (posizione soggetti, cosa tagliare, cosa tenere)\n"
        "- sharpness_targets: adattivi (es. volto+cibo se c'è una persona; solo cibo se piatto statico)\n"
        "- preserve_soft_background: true se lo sfondo è già sfocato/bokeh\n"
        "- preserve_elements: elenca logo, bandierina, patatine e altri elementi brand visibili\n"
        "- light_adjustments: SOLO numeri float (mai frasi). exposure/contrast/saturation tra -0.15 e 0.15; "
        "sharpness 0.0-0.3. Per +0.2 EV circa usa exposure ~0.08-0.12\n"
        "- Tutti i campi testuali in italiano\n"
        f"FORMATO TARGET: {fmt}\n"
        f"CANALI: {channels_label(ch)}\n"
        f"Categoria: {business_category or 'non specificata'}\n"
        f"Content pillar: {content_pillar}\n"
    )


def run_image_edit_plan(
    image_path: Path,
    *,
    settings: Settings,
    business_category: str | None = None,
    platform: Platform = Platform.INSTAGRAM,
    media_format: MediaFormat = MediaFormat.POST,
    channels: list[Platform] | None = None,
) -> ImageEditPlan:
    """Analisi visiva pre-edit → piano foto-specifico."""
    if not api_configured(api_key=settings.vision_api_key, model=settings.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Image Edit Plan")
    plan_model = (settings.visual_edit_plan_model or settings.vision_model or "").strip()
    if not plan_model:
        raise ValueError("VISION_MODEL o VISUAL_EDIT_PLAN_MODEL richiesti per Image Edit Plan")
    pillar = pillar_for_category(business_category)
    user = build_image_edit_plan_user_prompt(
        business_category=business_category,
        platform=platform,
        media_format=media_format,
        content_pillar=pillar,
        channels=channels,
    )
    data = chat_vision_json(
        image_path=image_path,
        system_message=build_system_message(load_story_agent_config()),
        user_prompt=user,
        api_key=settings.vision_api_key,
        model=plan_model,
        api_base_url=settings.vision_api_base_url,
        max_tokens=800,
        settings=settings,
    )
    return ImageEditPlan.from_dict(data)
