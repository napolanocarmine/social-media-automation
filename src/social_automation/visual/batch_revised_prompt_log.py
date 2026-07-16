"""Log diagnostico revised_prompt (gpt-5.5 → gpt-image) per batch."""

from __future__ import annotations

from pathlib import Path


def revised_prompt_log_path(output_dir: Path, batch_id: int) -> Path:
    return output_dir / "logs" / f"batch-{batch_id}-revised-prompts.log"


def append_batch_revised_prompt_log(
    output_dir: Path,
    batch_id: int,
    *,
    item_index: int,
    image_id: int,
    source_asset_id: str,
    source_asset_name: str,
    method: str,
    revised_prompt: str,
) -> Path:
    """Append revised_prompt completo in un file dedicato al batch."""
    path = revised_prompt_log_path(output_dir, batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"=== batch #{batch_id} item {item_index} "
        f"image_id={image_id} file={source_asset_name} "
        f"asset_id={source_asset_id} method={method} ===\n"
    )
    with path.open("a", encoding="utf-8") as fp:
        fp.write(header)
        fp.write(revised_prompt.strip())
        fp.write("\n---\n")
    return path


def revised_prompt_from_process_output(out: dict) -> str | None:
    """Estrae revised_prompt dal dict restituito da process_drive_asset."""
    for key in ("visual_review", "retouch"):
        block = out.get(key)
        if not isinstance(block, dict):
            continue
        edit_plan = block.get("edit_plan")
        if not isinstance(edit_plan, dict):
            continue
        text = edit_plan.get("revised_prompt")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None
