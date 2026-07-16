from social_automation.canva.templates import resolve_template_id
from social_automation.models import MediaFormat


def test_resolve_template_id_prefers_category_override() -> None:
    cfg = {
        "templates": {"instagram": {"default_template_id": "default_ig"}},
        "category_template_overrides": {"boss": {"instagram": "boss_ig"}},
    }
    template = resolve_template_id(cfg, platform="instagram", category="boss")
    assert template == "boss_ig"


def test_resolve_template_id_falls_back_to_default() -> None:
    cfg = {
        "templates": {"facebook": {"default_template_id": "default_fb"}},
        "category_template_overrides": {"food": {"instagram": "food_ig"}},
    }
    template = resolve_template_id(cfg, platform="facebook", category="food")
    assert template == "default_fb"


def test_resolve_template_id_uses_shared_story_template_for_both_platforms() -> None:
    cfg = {
        "templates": {
            "instagram": {"default_template_id": "default_ig"},
            "facebook": {"default_template_id": "default_fb"},
            "story": {"default_template_id": "shared_story"},
        },
    }
    assert (
        resolve_template_id(
            cfg,
            platform="instagram",
            media_format=MediaFormat.STORY,
        )
        == "shared_story"
    )
    assert (
        resolve_template_id(
            cfg,
            platform="facebook",
            media_format=MediaFormat.STORY,
        )
        == "shared_story"
    )


def test_resolve_template_id_story_category_override_wins() -> None:
    cfg = {
        "templates": {
            "instagram": {"default_template_id": "default_ig"},
            "story": {"default_template_id": "default_story"},
        },
        "category_template_overrides": {
            "boss": {"instagram": "boss_ig", "story": "boss_story"},
        },
    }
    template = resolve_template_id(
        cfg,
        platform="instagram",
        category="boss",
        media_format=MediaFormat.STORY,
    )
    assert template == "boss_story"


def test_resolve_template_id_post_default_unaffected_by_story_section() -> None:
    cfg = {
        "templates": {
            "instagram": {"default_template_id": "default_ig"},
            "story": {"default_template_id": "shared_story"},
        },
    }
    assert (
        resolve_template_id(cfg, platform="instagram", media_format=MediaFormat.POST)
        == "default_ig"
    )
