"""Test risoluzione post vs story in dispatch."""

from __future__ import annotations

from social_automation.brand.copy_pack import planning_detail_with_caption
from social_automation.models import MediaFormat
from social_automation.scheduling.dispatch_format import resolve_dispatch_media_format


def test_resolve_prefers_planning_detail_over_blob_path() -> None:
    detail = planning_detail_with_caption(media_format=MediaFormat.STORY)
    row = {
        "detail": detail,
        "image_path": "https://blob.vercel-storage.com/processed/instagram/42.jpg",
        "render_ig": 1,
        "render_ig_story": 1,
    }
    assert resolve_dispatch_media_format(row) == MediaFormat.STORY


def test_resolve_post_from_planning_detail() -> None:
    detail = planning_detail_with_caption("Ciao feed", media_format=MediaFormat.POST)
    row = {
        "detail": detail,
        "image_path": "output/processed/stories/food_x_story.jpg",
        "render_ig_story": 1,
    }
    assert resolve_dispatch_media_format(row) == MediaFormat.POST


def test_resolve_story_only_render_flags() -> None:
    row = {
        "detail": "",
        "image_path": "https://blob.vercel-storage.com/processed/instagram/7.jpg",
        "render_ig_story": 1,
        "render_fb_story": 0,
        "render_ig": 0,
        "render_fb": 0,
    }
    assert resolve_dispatch_media_format(row) == MediaFormat.STORY


def test_resolve_force_story() -> None:
    row = {
        "detail": planning_detail_with_caption("cap", media_format=MediaFormat.POST),
        "image_path": "output/processed/ig/x.jpg",
    }
    assert resolve_dispatch_media_format(row, force_story=True) == MediaFormat.STORY


def test_resolve_blob_story_path_fallback() -> None:
    row = {
        "detail": "",
        "image_path": "https://x.blob/processed/stories/instagram/9_story.jpg",
    }
    assert resolve_dispatch_media_format(row) == MediaFormat.STORY
