from __future__ import annotations

import json
from pathlib import Path

import httpx

from social_automation.models import Platform
from social_automation.validation.image_gate import (
    validate_image_for_publish,
    vision_validation_configured,
)


def test_vision_disabled_without_key(tmp_path: Path) -> None:
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    r = validate_image_for_publish(img, Platform.INSTAGRAM, api_key="", model="")
    assert r.success
    assert "disattivata" in (r.reason or "").lower()


def test_vision_parses_json_response(tmp_path: Path, monkeypatch) -> None:
    img = tmp_path / "b.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {"message": {"content": json.dumps({"pass": True, "reason": "ok"})}}
                ]
            }

    def fake_post(self, url, json=None, headers=None):
        return FakeResp()

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    r = validate_image_for_publish(
        img,
        Platform.INSTAGRAM,
        api_key="sk-test",
        model="gpt-4o-mini",
    )
    assert r.success
    assert r.reason == "ok"


def test_vision_validation_configured() -> None:
    assert vision_validation_configured(api_key="k", model="m")
    assert not vision_validation_configured(api_key="", model="m")
