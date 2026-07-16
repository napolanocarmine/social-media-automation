from __future__ import annotations

from social_automation.processing.image_adjust import image_api_size_for_crop
from social_automation.settings import Settings
from social_automation.visual.image_generation import _edit_request_data


def test_image_api_size_for_crop_modes() -> None:
    assert image_api_size_for_crop("instagram_4_5") == "1024x1536"
    assert image_api_size_for_crop("story_9_16") == "1024x1792"
    assert image_api_size_for_crop("facebook_context") == "1536x1024"


def test_edit_request_uses_high_fidelity_and_crop_size() -> None:
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_image_model="gpt-image-1",
        visual_image_input_fidelity="high",
    )
    data = _edit_request_data(settings, prompt="subtle edit", crop_mode="instagram_4_5")
    assert data["input_fidelity"] == "high"
    assert data["size"] == "1024x1536"
    assert data["output_format"] == "jpeg"


def test_edit_request_story_crop_size() -> None:
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_image_model="gpt-image-1",
    )
    data = _edit_request_data(settings, prompt="crop", crop_mode="story_9_16")
    assert data["size"] == "1024x1792"


def test_edit_request_respects_explicit_size() -> None:
    settings = Settings(
        vision_api_key="sk-test",
        vision_model="gpt-4o-mini",
        visual_image_model="gpt-image-1",
        visual_image_size="1024x1536",
    )
    data = _edit_request_data(settings, prompt="crop", crop_mode="story_9_16")
    assert data["size"] == "1024x1536"
