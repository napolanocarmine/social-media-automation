from __future__ import annotations

from social_automation.brand.loader import load_story_agent_config
from social_automation.brand.prompt_context import (
    build_copy_user_prompt,
    build_produce_user_prompt,
    channels_label,
    copy_format_label,
    image_format_label,
)
from social_automation.models import MediaFormat, Platform


def test_image_format_label_ig_post() -> None:
    assert image_format_label(
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    ) == "Instagram Post 1080x1350"


def test_copy_format_label_story() -> None:
    assert copy_format_label(MediaFormat.STORY) == "Story"


def test_channels_label_both() -> None:
    ch = [Platform.INSTAGRAM, Platform.FACEBOOK]
    assert channels_label(ch) == "Instagram + Facebook"


def test_build_produce_prompt_includes_ui_params() -> None:
    cfg = load_story_agent_config()
    prompt = build_produce_user_prompt(
        cfg,
        marketing_objective="Engagement",
        channels=[Platform.INSTAGRAM, Platform.FACEBOOK],
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
    )
    assert "/produce" in prompt
    assert "OBIETTIVO:\nEngagement" in prompt or "OBIETTIVO:\n  Engagement" in prompt
    assert "Instagram + Facebook" in prompt
    assert "Instagram Post 1080x1350" in prompt
    assert "la stessa foto scattata meglio" in prompt
    assert "Genera direttamente l'immagine finale ottimizzata" in prompt
    assert "crop corretto per Instagram" in prompt


def test_build_image_edit_prompt_uses_dedicated_task_template() -> None:
    from social_automation.settings import Settings
    from social_automation.visual.prompts import (
        build_image_edit_instructions,
        build_image_edit_prompt,
        build_image_edit_user_prompt,
    )

    review = {"reasoning": "nitidezza", "suggested_format": "instagram_4_5"}
    kwargs = dict(
        review=review,
        business_category="food",
        platform=Platform.INSTAGRAM,
        media_format=MediaFormat.POST,
        content_pillar="food",
        marketing_objectives=["Engagement"],
        channels=[Platform.INSTAGRAM, Platform.FACEBOOK],
    )
    no_kb = Settings(visual_edit_include_kb=False, visual_hybrid_tone_pipeline=False)
    instructions = build_image_edit_instructions(no_kb)
    user = build_image_edit_user_prompt(**kwargs, settings=no_kb)
    legacy = build_image_edit_prompt(**kwargs)

    assert instructions == ""
    assert "EDIT the attached photograph" in user
    assert "Image Editing Task" in user
    assert "Preserve 100% of the original image content" in user
    assert "Instagram Feed 4:5 (1080x1350)" in user
    assert "Instagram + Facebook" in user
    assert "l'hamburger" in user
    assert "bandierina" in user
    assert "Lightroom professionale" in user
    assert "/produce" not in user
    assert "Note review visiva" not in user
    assert "--- KNOWLEDGE BASE" in legacy

    with_kb = Settings(visual_edit_include_kb=True)
    kb_instructions = build_image_edit_instructions(with_kb)
    assert "Story AI Assistant" in kb_instructions or "Story non vende" in kb_instructions


def test_build_copy_prompt_includes_ui_params() -> None:
    cfg = load_story_agent_config()
    prompt = build_copy_user_prompt(
        cfg,
        marketing_objective="Community",
        channels=[Platform.INSTAGRAM, Platform.FACEBOOK],
        media_format=MediaFormat.POST,
    )
    assert "/copy" in prompt
    assert "Community" in prompt
    assert "Instagram + Facebook" in prompt
    assert "FORMATO:\nPost" in prompt or "FORMATO:\n  Post" in prompt
    assert "Story vende compagnia" in prompt
