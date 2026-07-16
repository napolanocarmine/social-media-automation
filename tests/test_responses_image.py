from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from social_automation.settings import Settings
from social_automation.visual import responses_image as ri
from social_automation.visual.models import ImageEditApiResult


def _write_test_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), color=(120, 80, 40)).save(path, format="JPEG")


def test_responses_payload_uses_gpt_image_15_with_high_fidelity() -> None:
    tool = ri._image_generation_tool(
        Settings(
            vision_api_key="sk-test",
            visual_responses_image_model="gpt-image-1.5",
            visual_image_input_fidelity="high",
            visual_image_quality="high",
        ),
        crop_mode="instagram_4_5",
    )
    assert tool["type"] == "image_generation"
    assert tool["model"] == "gpt-image-1.5"
    assert tool["action"] == "edit"
    assert tool["input_fidelity"] == "high"
    assert tool["quality"] == "high"
    assert tool["size"] == "1024x1536"


def test_responses_payload_story_crop_uses_9_16_api_size() -> None:
    tool = ri._image_generation_tool(
        Settings(vision_api_key="sk-test"),
        crop_mode="story_9_16",
    )
    assert tool["size"] == "1024x1792"


def test_responses_payload_omits_fidelity_for_gpt_image_2() -> None:
    tool = ri._image_generation_tool(
        Settings(
            vision_api_key="sk-test",
            visual_responses_image_model="gpt-image-2",
            visual_image_input_fidelity="high",
        ),
        crop_mode="instagram_4_5",
    )
    assert tool["model"] == "gpt-image-2"
    assert "input_fidelity" not in tool


def test_edit_image_via_responses_saves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "in.jpg"
    dest = tmp_path / "out.jpg"
    _write_test_jpeg(source)
    fake_jpeg = Image.new("RGB", (1080, 1350), color=(10, 20, 30))
    buf = __import__("io").BytesIO()
    fake_jpeg.save(buf, format="JPEG")
    payload_b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "output": [
                    {
                        "type": "image_generation_call",
                        "status": "completed",
                        "result": payload_b64,
                        "revised_prompt": "Edit photo: sharpen burger only, preserve background bokeh.",
                    }
                ]
            }

    fake_client = MagicMock()
    fake_client.__enter__ = lambda s: s
    fake_client.__exit__ = lambda *a: None
    fake_client.post.return_value = FakeResp()
    monkeypatch.setattr(ri.httpx, "Client", lambda **k: fake_client)

    settings = Settings(
        vision_api_key="sk-test",
        visual_responses_model="gpt-5.5",
        visual_responses_image_model="gpt-image-1.5",
        visual_edit_include_kb=False,
    )
    result = ri.edit_image_via_responses(
        source,
        instructions="",
        user_prompt="/produce test",
        dest_path=dest,
        settings=settings,
        crop_mode="instagram_4_5",
    )
    assert isinstance(result, ImageEditApiResult)
    assert result.path == dest
    assert result.revised_prompt is not None
    assert "sharpen burger" in result.revised_prompt
    assert dest.is_file()
    post = fake_client.post.call_args
    body = post.kwargs["json"]
    assert body["model"] == "gpt-5.5"
    assert "instructions" not in body
    assert body["tool_choice"] == {"type": "image_generation"}
    assert body["tools"][0]["model"] == "gpt-image-1.5"
    assert body["tools"][0]["action"] == "edit"
    assert body["tools"][0]["size"] == "1024x1536"
    assert body["input"][0]["content"][1]["detail"] == "original"
