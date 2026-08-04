"""Upload manuale da browser: validazione dimensioni, resize, registrazione DB."""

from __future__ import annotations

import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from social_automation.config_loaders import load_category_aliases
from social_automation.db.store import (
    add_batch_item,
    create_batch,
    record_processed_artifacts,
    set_image_manual_publication_valid,
    update_vision_eval,
)
from social_automation.drive.selection import normalize_business_category
from social_automation.models import MediaFormat, Platform
from social_automation.processing.image_adjust import (
    crop_mode_for_platform,
    normalize_image_orientation,
)
from social_automation.services.batch_runner import DEFAULT_CATEGORIES_CONFIG
from social_automation.services.media import maybe_persist_processed_media_to_blob
from social_automation.settings import Settings
from social_automation.visual.postprocess import copy_or_finalize_for_crop_mode

_LOG = logging.getLogger(__name__)

ResizeAction = Literal["keep", "resize"]


def expected_dimensions(platform: Platform, media_format: MediaFormat) -> tuple[int, int]:
    from social_automation.processing.image_adjust import TARGET_SIZE_BY_CROP

    crop_mode = crop_mode_for_platform(platform, media_format)
    return TARGET_SIZE_BY_CROP[crop_mode]


def read_image_dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as im:
        oriented = normalize_image_orientation(im)
        return oriented.size


def validate_upload_dimensions(
    width: int,
    height: int,
    *,
    platform: Platform,
    media_format: MediaFormat,
) -> dict[str, Any]:
    target_w, target_h = expected_dimensions(platform, media_format)
    valid = width == target_w and height == target_h
    return {
        "valid": valid,
        "width": width,
        "height": height,
        "expected_width": target_w,
        "expected_height": target_h,
        "expected_label": f"{target_w}×{target_h}",
    }


def validate_upload_bytes(
    data: bytes,
    *,
    platform: Platform,
    media_format: MediaFormat,
) -> dict[str, Any]:
    width, height = read_image_dimensions(data)
    result = validate_upload_dimensions(
        width,
        height,
        platform=platform,
        media_format=media_format,
    )
    return result


def _save_upload_bytes(data: bytes, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(data)) as im:
        rgb = normalize_image_orientation(im).convert("RGB")
        rgb.save(dest, format="JPEG", quality=95, optimize=True)
    return dest


def _apply_resize_action(
    source: Path,
    dest: Path,
    *,
    platform: Platform,
    media_format: MediaFormat,
    action: ResizeAction,
) -> Path:
    if action == "keep":
        if source.resolve() != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        return dest
    crop_mode = crop_mode_for_platform(platform, media_format)
    return copy_or_finalize_for_crop_mode(
        source,
        dest,
        crop_mode,
        allow_center_crop=True,
    )


def register_uploaded_image(
    settings: Settings,
    *,
    source_path: Path,
    image_name: str,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str,
    marketing_objectives: list[str],
    channels: list[str],
    resize_action: ResizeAction = "keep",
) -> dict[str, Any]:
    """Registra upload senza AI, auto-approvato e pronto per pianificazione."""
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex[:12]
    processed_path = output_dir / f"upload_{upload_id}.jpg"

    _apply_resize_action(
        source_path,
        processed_path,
        platform=platform,
        media_format=media_format,
        action=resize_action,
    )

    w, h = read_image_dimensions(processed_path.read_bytes())
    validation = validate_upload_dimensions(w, h, platform=platform, media_format=media_format)

    meta = {
        "platform": platform.value,
        "media_format": media_format.value,
        "business_category": business_category,
        "source_file": str(source_path),
        "output_file": str(processed_path),
        "mode": "manual_upload",
        "upload_id": upload_id,
        "marketing_objectives": marketing_objectives,
        "channels": channels,
        "resize_action": resize_action,
        "dimensions_valid": validation["valid"],
    }

    image_id = record_processed_artifacts(
        settings.db_path,
        image_name=image_name.strip() or source_path.name,
        image_path=processed_path,
        source_asset_id=f"upload_{upload_id}",
        source_asset_name=image_name.strip() or source_path.name,
        business_category=business_category,
        metadata_payload=meta,
        original_path=str(source_path),
    )

    blob_urls = maybe_persist_processed_media_to_blob(
        settings.db_path,
        image_id=image_id,
        settings=settings,
        processed_path=processed_path,
        source_path=source_path,
        original_path=str(source_path),
        source_asset_id=f"upload_{upload_id}",
        platform=platform.value,
        media_format=media_format.value,
    )
    if blob_urls.get("path"):
        processed_path = Path(blob_urls["path"])

    set_image_manual_publication_valid(settings.db_path, image_id=image_id, value=1)
    update_vision_eval(
        settings.db_path,
        image_id=image_id,
        vision_pass=1,
        reason="Upload manuale auto-approvato",
    )

    return {
        "image_id": image_id,
        "name": image_name.strip() or source_path.name,
        "processed_file": str(processed_path),
        "dimensions": validation,
        "platform": platform.value,
        "media_format": media_format.value,
    }


def start_upload_ai_batch(
    settings: Settings,
    *,
    category: str,
    platform: Platform,
    media_format: MediaFormat,
    items: list[dict[str, Any]],
    marketing_objectives: list[str] | None = None,
    channels: list[str] | None = None,
    visual_image_input_fidelity: str | None = None,
) -> int:
    """Avvia batch AI per file caricati manualmente (local_path nel payload)."""
    if not items:
        raise ValueError("Nessun file da elaborare")

    aliases = (
        load_category_aliases(DEFAULT_CATEGORIES_CONFIG)
        if DEFAULT_CATEGORIES_CONFIG.exists()
        else {}
    )
    business_category = normalize_business_category(category.strip(), aliases)
    db_path = settings.db_path

    batch_id = create_batch(
        db_path,
        category=category.strip(),
        platform=platform,
        requested_count=len(items),
        media_format=media_format,
        note="manual-upload-ai",
    )

    for idx, item in enumerate(items):
        payload = {
            "source_type": "upload",
            "local_path": str(item["local_path"]),
            "name": str(item.get("name") or Path(str(item["local_path"])).name),
            "mime_type": str(item.get("mime_type") or "image/jpeg"),
            "marketing_objectives": list(marketing_objectives or []),
            "channels": list(channels or []),
            "business_category": business_category,
            "resize_action": str(item.get("resize_action") or "keep"),
            "upload_id": str(item.get("upload_id") or ""),
        }
        if visual_image_input_fidelity:
            payload["visual_image_input_fidelity"] = visual_image_input_fidelity
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=idx + 1,
            status="queued",
            source_asset_id=str(item.get("upload_id") or f"upload_{idx}"),
            source_asset_name=str(payload["name"]),
            business_category=business_category,
            payload=payload,
            media_format=media_format,
        )

    return int(batch_id)


def parse_resize_actions(raw: str | None) -> dict[str, ResizeAction]:
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("resize_actions non è JSON valido") from exc
    if not isinstance(parsed, dict):
        raise ValueError("resize_actions deve essere un oggetto JSON")
    out: dict[str, ResizeAction] = {}
    for key, value in parsed.items():
        action = str(value).strip().lower()
        if action not in {"keep", "resize"}:
            raise ValueError(f"Azione resize non valida per {key}: {value}")
        out[str(key)] = action  # type: ignore[assignment]
    return out


def parse_objectives_list(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if isinstance(parsed, list):
        return [str(o).strip() for o in parsed if str(o).strip()]
    raise ValueError("marketing_objectives deve essere un array JSON")
