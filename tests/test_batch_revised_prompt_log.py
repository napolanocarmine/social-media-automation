from __future__ import annotations

from social_automation.visual.batch_revised_prompt_log import (
    append_batch_revised_prompt_log,
    revised_prompt_from_process_output,
    revised_prompt_log_path,
)


def test_revised_prompt_from_process_output() -> None:
    out = {
        "visual_review": {
            "edit_plan": {"revised_prompt": "Sharpen burger only."},
        }
    }
    assert revised_prompt_from_process_output(out) == "Sharpen burger only."


def test_append_batch_revised_prompt_log(tmp_path) -> None:
    path = append_batch_revised_prompt_log(
        tmp_path,
        42,
        item_index=1,
        image_id=99,
        source_asset_id="abc",
        source_asset_name="IMG_1.JPG",
        method="ai_edited_hybrid",
        revised_prompt="Full prompt text here.",
    )
    assert path == revised_prompt_log_path(tmp_path, 42)
    text = path.read_text(encoding="utf-8")
    assert "batch #42" in text
    assert "image_id=99" in text
    assert "Full prompt text here." in text
    assert text.endswith("---\n")
